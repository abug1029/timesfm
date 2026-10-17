#!/usr/bin/env python3
"""backfill_prescreen.py — 批量处理积压的 prescreen 提案。

用法:
  source .venv/bin/activate
  python scripts/backfill_prescreen.py [--max N] [--cooldown-hours N] [--workers N]
    [--dry-run] [--force] [--resume] [--reset] [--queue-path PATH] [--timeout-min N]

断点续跑: 默认自动恢复上次进度; --reset 清空进度重新开始。
"""
import argparse
import glob
import json
import logging
import os
import signal
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

FM_ROOT = Path(__file__).resolve().parent.parent
if str(FM_ROOT) not in sys.path:
    sys.path.insert(0, str(FM_ROOT))

# ── 路径常量 ────────────────────────────────────────
STATE_FILE = FM_ROOT / "data" / "cache" / "backfill_prescreen_state.json"
LOG_FILE = FM_ROOT / "logs" / "backfill_prescreen.log"
SCRIPT_VERSION = "1.0.0"

# ── 优雅退出 ────────────────────────────────────────
_shutdown = False


def _sig_handler(signum, frame):
    global _shutdown
    _shutdown = True
    logging.info("收到信号 %s，等待当前任务完成后退出", signum)


signal.signal(signal.SIGINT, _sig_handler)
signal.signal(signal.SIGTERM, _sig_handler)


# ── 日志配置 ────────────────────────────────────────
def setup_logging():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_log = LOG_FILE.parent / f"backfill_prescreen_{ts}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(run_log, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    logging.info("日志: %s", run_log)
    return run_log


# ── 状态持久化 ──────────────────────────────────────
def load_state():
    """加载进度状态文件。"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logging.warning("状态文件损坏，重新初始化")
    return {
        "processed": [],
        "last_run": None,
        "stats": {"total": 0, "success": 0, "failed": 0, "enqueued": 0, "skipped": 0},
        "version": SCRIPT_VERSION,
    }


def save_state(state):
    """原子写入状态文件（tmp + rename）。"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


# ── Laya 健康检查 ──────────────────────────────────
def check_laya_health(timeout=10):
    """检查 Laya 服务是否可达。"""
    try:
        from data.config import _env_nonempty
    except ImportError:
        logging.warning("无法导入 data.config，跳过 Laya 健康检查")
        return True

    base_url = _env_nonempty("LAYA_BASE_URL") or "http://10.1.1.67:8000"
    health_url = base_url + "/health"

    try:
        import requests
        resp = requests.get(health_url, timeout=timeout)
        if resp.status_code == 200:
            logging.info("Laya 服务健康: %s", health_url)
            return True
        logging.error("Laya 健康检查返回 %d", resp.status_code)
        return False
    except requests.exceptions.ConnectionError:
        logging.error("Laya 服务不可达: %s", health_url)
        return False
    except Exception as e:
        logging.error("Laya 健康检查异常: %s", e)
        return False


# ── Supervisor 收割检查 ────────────────────────────
def check_supervisor_harvest():
    """检查 supervisor 是否正在 harvest。本脚本只读不冲突。"""
    state_path = FM_ROOT / "data" / "supervisor_state.json"
    if not state_path.exists():
        return False
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        phase = data.get("phase", "")
        if phase == "harvest":
            logging.info("Supervisor 正在 harvest 阶段，本脚本只读不冲突，继续")
            return True
    except (json.JSONDecodeError, OSError, KeyError):
        pass
    return False


# ── 冷却期检查 ─────────────────────────────────────
def should_skip(prescreen_path, cooldown_hours, force):
    """检查是否应跳过（已有 success 或在冷却期内）。"""
    if not prescreen_path.exists():
        return False

    try:
        data = json.loads(prescreen_path.read_text(encoding="utf-8"))
        status = data.get("status")

        # success 永远跳过
        if status == "success":
            return True

        # force 模式忽略冷却期
        if force:
            return False

        # 检查冷却期
        ts = data.get("ts")
        if ts:
            try:
                last_attempt = datetime.fromisoformat(ts)
                if datetime.now(timezone.utc) - last_attempt < timedelta(hours=cooldown_hours):
                    return True
            except ValueError:
                pass

        return False
    except (json.JSONDecodeError, OSError):
        # 损坏文件 → 允许重试
        return False


# ── 提取 symbol ────────────────────────────────────
def extract_symbol(proposal_path):
    """从 proposal 文件提取 symbol。"""
    p = Path(proposal_path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("symbol", p.stem.split("_")[0])
    except Exception:
        return p.stem.split("_")[0]


# ── 加载辅助数据 ────────────────────────────────────
def load_verdict_history():
    """加载 aligned_verdicts.jsonl 历史裁决。"""
    path = FM_ROOT / "task_FM" / "config" / "aligned_verdicts.jsonl"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except Exception as e:
        logging.warning("加载历史裁决失败: %s", e)
        return []


def load_covariate_menu():
    """加载 covariate_menu.inc.md。"""
    path = FM_ROOT / "task_FM" / "covariate_menu.inc.md"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return {"text": f.read()}
    except Exception as e:
        logging.warning("加载协变量菜单失败: %s", e)
        return {}


# ── 线程安全统计 ────────────────────────────────────
class Stats:
    def __init__(self):
        self.lock = Lock()
        self.total = 0
        self.success = 0
        self.skipped = 0
        self.failed = 0
        self.enqueued = 0

    def inc(self, field):
        with self.lock:
            setattr(self, field, getattr(self, field) + 1)

    def snapshot(self):
        with self.lock:
            return {
                "total": self.total,
                "success": self.success,
                "failed": self.failed,
                "enqueued": self.enqueued,
                "skipped": self.skipped,
            }


# ── 处理单个提案 ────────────────────────────────────
def process_proposal(proposal_path, stats, queue_path, queue_lock, verdict_history, covariate_menu):
    """处理单个提案，返回结果标签。"""
    try:
        symbol = extract_symbol(proposal_path)
        proposal = json.loads(Path(proposal_path).read_text(encoding="utf-8"))

        from cascade.typesafe_prescreen import prescreen_and_save

        result = prescreen_and_save(
            proposal=proposal,
            proposal_path=str(proposal_path),
            symbol=symbol,
            verdict_history=verdict_history,
            covariate_menu=covariate_menu,
        )

        status = result.get("status", "unknown")
        if status == "success":
            stats.inc("success")
            # 通过的提案入队慢环
            if not result.get("skip_suggested"):
                entry = {
                    "proposal_path": str(proposal_path),
                    "prescreen": result,
                    "enqueued_at": datetime.now(timezone.utc).isoformat(),
                }
                with queue_lock:
                    with open(queue_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                stats.inc("enqueued")
            return "success"
        else:
            stats.inc("failed")
            return status

    except Exception as e:
        logging.error("处理失败 %s: %s\n%s", proposal_path, e, traceback.format_exc())
        stats.inc("failed")
        return "error"


# ── 主函数 ──────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="批量处理积压的 prescreen 提案")
    parser.add_argument("--max", type=int, default=500, help="最多处理 N 个提案（默认 500）")
    parser.add_argument("--workers", type=int, default=5, help="线程池大小（默认 5）")
    parser.add_argument("--dry-run", action="store_true", help="只扫描不执行")
    parser.add_argument("--force", action="store_true", help="忽略冷却期强制重试")
    parser.add_argument("--resume", action="store_true", help="继续上次运行（默认行为）")
    parser.add_argument("--reset", action="store_true", help="清空进度重新开始")
    parser.add_argument("--queue-path", type=str, default="task_FM/config/queue.jsonl", help="慢环队列路径")
    parser.add_argument("--timeout-min", type=int, default=30, help="单次运行最大时长（分钟，默认 30）")
    args = parser.parse_args()

    log_path = setup_logging()
    logging.info("=" * 60)
    logging.info("backfill_prescreen v%s 启动", SCRIPT_VERSION)
    logging.info("参数: max=%d cooldown=%dh workers=%d dry_run=%s force=%s reset=%s timeout=%dmin",
                 args.max, args.cooldown_hours, args.workers, args.dry_run, args.force, args.reset, args.timeout_min)

    # ── 检查上次运行时间 ─────────────────────────
    state = load_state()
    if state["last_run"] and not args.reset:
        last_run = datetime.fromisoformat(state["last_run"])
        gap = datetime.now() - last_run
        if gap < timedelta(hours=1):
            logging.warning("上次运行在 %s 前（%s），如需重新运行请确认或加 --reset",
                            last_run.strftime("%H:%M:%S"), gap)

    if args.reset:
        logging.info("--reset: 清空进度重新开始")
        state = {
            "processed": [],
            "last_run": None,
            "stats": {"total": 0, "success": 0, "failed": 0, "enqueued": 0, "skipped": 0},
            "version": SCRIPT_VERSION,
        }

    processed_set = set(state.get("processed", []))
    logging.info("已处理: %d 条", len(processed_set))

    # ── Laya 健康检查 ────────────────────────────
    if not args.dry_run:
        if not check_laya_health():
            logging.error("Laya 服务不可达，退出。使用 --dry-run 仅扫描。")
            sys.exit(1)

    # ── Supervisor 检查 ──────────────────────────
    check_supervisor_harvest()

    # ── 扫描所有 proposals ───────────────────────
    pattern = str(FM_ROOT / "task_FM" / "experiments" / "run_*" / "results" / "**" / "proposals" / "*.json")
    all_proposals = glob.glob(pattern, recursive=True)
    all_proposals = [p for p in all_proposals if not p.endswith(".prescreen.json")]
    logging.info("扫描到 %d 个提案", len(all_proposals))

    # ── 过滤 ─────────────────────────────────────
    to_process = []
    for p in sorted(all_proposals):
        if p in processed_set:
            continue
        prescreen_path = Path(p).with_suffix(".prescreen.json")
        if should_skip(prescreen_path, args.cooldown_hours, args.force):
            continue
        to_process.append(p)
        if len(to_process) >= args.max:
            break

    logging.info("待处理: %d", len(to_process))

    if args.dry_run:
        logging.info("Dry run 模式，显示前 20 个待处理提案:")
        for p in to_process[:20]:
            logging.info("  - %s", p)
        logging.info("... 共 %d 个", len(to_process))
        return

    if not to_process:
        logging.info("无需处理的提案，退出")
        return

    # ── 初始化 ───────────────────────────────────
    stats = Stats()
    stats.total = len(to_process)
    queue_lock = Lock()
    queue_path = FM_ROOT / args.queue_path
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    verdict_history = load_verdict_history()
    covariate_menu = load_covariate_menu()
    logging.info("加载 %d 条历史裁决, covariate_menu: %s",
                 len(verdict_history), "有" if covariate_menu else "无")

    start_time = time.monotonic()
    timeout_secs = args.timeout_min * 60

    # ── 线程池处理 ───────────────────────────────
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_proposal, p, stats, queue_path, queue_lock,
                verdict_history, covariate_menu
            ): p
            for p in to_process
        }

        for i, future in enumerate(as_completed(futures), 1):
            proposal_path = futures[future]

            elapsed = time.monotonic() - start_time
            if elapsed > timeout_secs:
                logging.warning("运行时长超过 %d 分钟，优雅退出", args.timeout_min)
                for f in futures:
                    if not f.done():
                        f.cancel()
                break

            if _shutdown:
                logging.info("收到退出信号，停止接收新任务")
                for f in futures:
                    if not f.done():
                        f.cancel()
                break

            processed_set.add(proposal_path)
            if i % 10 == 0:
                state["processed"] = list(processed_set)
                state["stats"] = stats.snapshot()
                save_state(state)

            if i % 50 == 0 or i == len(to_process):
                snap = stats.snapshot()
                logging.info(
                    "进度: %d/%d (success=%d failed=%d enqueued=%d) elapsed=%.0fs",
                    i, len(to_process), snap["success"], snap["failed"],
                    snap["enqueued"], elapsed
                )

    # ── 最终统计 ─────────────────────────────────
    elapsed = time.monotonic() - start_time
    snap = stats.snapshot()
    state["processed"] = list(processed_set)
    state["stats"] = snap
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["version"] = SCRIPT_VERSION
    save_state(state)

    logging.info("=" * 60)
    logging.info("完成: total=%d success=%d failed=%d enqueued=%d elapsed=%.0fs",
                 snap["total"], snap["success"], snap["failed"], snap["enqueued"], elapsed)
    logging.info("状态文件: %s", STATE_FILE)
    logging.info("队列文件: %s", queue_path)
    logging.info("=" * 60)


if __name__ == "__main__":
    main()
