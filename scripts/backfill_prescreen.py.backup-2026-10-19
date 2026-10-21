#!/usr/bin/env python3
"""backfill_prescreen.py — 批量处理积压的 prescreen 提案。

用法:
  source .venv/bin/activate
  python scripts/backfill_prescreen.py [--max N] [--workers N]
    [--dry-run] [--force] [--reset] [--queue-path PATH] [--timeout-min N]
    [--skip-laya-check]

断点续跑: 默认自动恢复上次进度; --reset 清空进度重新开始。
--force: 强制重跑所有提案（包括已成功状态）。
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
SCRIPT_VERSION = "2.1.0"

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
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
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
    """检查 Laya 服务是否可达。导入失败时 fail-closed（返回 False）。"""
    try:
        from data.config import _env_nonempty
    except ImportError:
        logging.error("无法导入 data.config，Laya 健康检查 fail-closed")
        return False

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


# ── 提案跳过逻辑 ───────────────────────────────────
def should_skip(proposal_path, force, processed_set):
    """检查是否应跳过。

    - 已在 processed_set（之前 run 中 success）→ 跳过，除非 force
    - 已有 prescreen 且 status == "success" → 跳过，除非 force
    - 其它状态（degraded/error/failed）→ 不跳过，允许重试
    """
    if force:
        return False

    if proposal_path in processed_set:
        return True

    prescreen_path = Path(proposal_path).with_suffix(".prescreen.json")
    if prescreen_path.exists():
        try:
            data = json.loads(prescreen_path.read_text(encoding="utf-8"))
            if data.get("status") == "success":
                return True
        except (json.JSONDecodeError, OSError):
            pass

    return False


# ── 从提案提取字段 ─────────────────────────────────
def extract_proposal_fields(proposal_path):
    """从 proposal JSON 提取 symbol, cov_override, proposal_id。

    返回 dict 或 None（解析失败时）。
    """
    try:
        data = json.loads(Path(proposal_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logging.error("无法解析提案 %s: %s", proposal_path, e)
        return None

    symbol = data.get("symbol", "")
    if not symbol:
        logging.warning("提案 %s 缺少 symbol 字段，跳过", proposal_path)
        return None

    cov_override = data.get("cov_override") or ""

    # 新协变量提案用 new_covariate.name
    if not cov_override:
        new_cov = data.get("new_covariate")
        if isinstance(new_cov, dict):
            cov_override = new_cov.get("name", "")

    proposal_id = data.get("proposal_id", Path(proposal_path).stem)

    return {
        "symbol": symbol,
        "cov_override": cov_override,
        "proposal_id": proposal_id,
        "proposal_data": data,
    }


def generate_variant_id(symbol, cov_override):
    """生成符合现网约定的 variant_id。

    复用现网身份链: resolve_cov_family + _experiment_fp_for + build_variant_id。
    与 sup_harvest.harvest_survivors 中 vid 生成完全一致 (spec W6.4)。
    """
    from cascade.cov_family import resolve_cov_family
    from cascade.experiment_fingerprint import build_variant_id
    import sup_evidence

    fam = resolve_cov_family({"cov_override": cov_override or None})
    fp = sup_evidence._experiment_fp_for(symbol, cov_override or "")
    if fam == "unknown" or fp is None:
        # W6.4: 身份不可得 → 返回 None，调用方拒绝
        return None
    return build_variant_id(symbol, fam, fp)


def extract_src_run(proposal_path):
    """从提案路径提取 run_* 目录名。"""
    p = Path(proposal_path)
    for parent in p.parents:
        if parent.name.startswith("run_"):
            return parent.name
    return os.path.basename(p.parent.parent)


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
        self.degraded = 0

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
                "degraded": self.degraded,
            }


# ── max_points 从 cadence 配置读取 ─────────────
def _get_max_points():
    """P2-4: 从 cadence 配置读取 aligned_max_points，回退 600。"""
    try:
        import sup_state
        import sup_paths as _sp
        cad = sup_state.load_goal(
            os.path.join(_sp.FM_ROOT, "scripts", "praxist_goal.yaml")
        ).get("cadence") or {}
        return sup_state._cad_int(cad, "aligned_max_points")
    except Exception:
        return 600


# ── 处理单个提案 ────────────────────────────────────
def process_proposal(proposal_path, stats, verdict_history, covariate_menu,
                     queue_path, dead, existing):
    """处理单个提案，返回 status_label。

    P2-5: success 且 vid 有效时立即入队（单个入队，锁保护），
    避免批末一次性入队因崩溃窗口丢失。
    """
    fields = extract_proposal_fields(proposal_path)
    if fields is None:
        stats.inc("failed")
        return "error"

    symbol = fields["symbol"]
    cov_override = fields["cov_override"]
    proposal_data = fields["proposal_data"]

    # ── Phase 2: 去重 pre-check ──────────────────────────────
    variant_id = generate_variant_id(symbol, cov_override)
    if variant_id is not None and variant_id in existing:
        stats.inc("skipped")
        return "skipped"
    # ─────────────────────────────────────────────────────────

    try:
        from cascade.typesafe_prescreen import prescreen_and_save

        result = prescreen_and_save(
            proposal=proposal_data,
            proposal_path=str(proposal_path),
            symbol=symbol,
            verdict_history=verdict_history,
            covariate_menu=covariate_menu,
        )

        status = result.get("status", "unknown")

        if status == "success":
            # P2-3: vid 检查通过后才计 success
            variant_id = generate_variant_id(symbol, cov_override)
            if variant_id is None:
                # P2-2: vid=None 时改写已写的 prescreen.json 为 error
                prescreen_path = Path(proposal_path).with_suffix(".prescreen.json")
                if prescreen_path.exists():
                    try:
                        data = json.loads(prescreen_path.read_text(encoding="utf-8"))
                        data["status"] = "error"
                        data["note"] = "variant_id generation failed (W6.4)"
                        prescreen_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                        logging.info("已改写 %s 为 error（vid 不可得）", prescreen_path.name)
                    except Exception as e:
                        logging.error("改写 prescreen.json 失败 %s: %s", prescreen_path, e)
                logging.warning(
                    "提案 %s prescreen success 但 variant_id 不可得 (W6.4)，标记 degraded",
                    proposal_path,
                )
                stats.inc("degraded")
                return "degraded"

            stats.inc("success")
            src_run = extract_src_run(proposal_path)

            queue_row = {
                "variant_id": variant_id,
                "symbol": symbol,
                "cov_override": cov_override or None,
                "max_points": _get_max_points(),
                "stage": "aligned",
                "checkpoint_path": "",
                "enqueued_at": datetime.now(timezone.utc).isoformat(),
                "src_run": src_run,
                "proposal_id": fields["proposal_id"],
                "version": int(proposal_data.get("version") or 1),
                "_proposal_path": str(proposal_path),
            }

            # P2-5: 立即入队（锁保护），避免崩溃窗口丢失
            try:
                import registry_lib as _rl
                added = _rl.queue_enqueue(queue_path, [queue_row], dead, existing)
                if added:
                    stats.inc("enqueued")
                    existing.add(variant_id)  # 防同批次重复
            except Exception as e:
                logging.error("入队失败 %s: %s", proposal_path, e)

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
    parser.add_argument("--force", action="store_true", help="强制重跑所有提案（包括已成功状态）")
    parser.add_argument("--reset", action="store_true", help="清空进度重新开始")
    parser.add_argument("--queue-path", type=str, default=None,
                        help="慢环队列路径（默认 data/cache/aligned_pending.jsonl）")
    parser.add_argument("--timeout-min", type=int, default=30, help="单次运行最大时长（分钟，默认 30）")
    parser.add_argument("--skip-laya-check", action="store_true", help="跳过 Laya 健康检查")
    args = parser.parse_args()

    log_path = setup_logging()
    logging.info("=" * 60)
    logging.info("backfill_prescreen v%s 启动", SCRIPT_VERSION)
    logging.info("参数: max=%d workers=%d dry_run=%s force=%s reset=%s timeout=%dmin skip_laya=%s",
                 args.max, args.workers, args.dry_run, args.force, args.reset,
                 args.timeout_min, args.skip_laya_check)

    # ── 加载状态 ─────────────────────────────────
    state = load_state()

    if args.reset:
        logging.info("--reset: 清空进度重新开始")
        state = {
            "processed": [],
            "last_run": None,
            "stats": {"total": 0, "success": 0, "failed": 0, "enqueued": 0, "skipped": 0},
            "version": SCRIPT_VERSION,
        }

    processed_set = set(state.get("processed", []))
    logging.info("已处理（success）: %d 条", len(processed_set))

    # ── 检查上次运行时间 ─────────────────────────
    if state.get("last_run") and not args.reset:
        try:
            last_run_str = state["last_run"]
            if last_run_str.endswith("Z"):
                last_run_str = last_run_str[:-1] + "+00:00"
            last_run = datetime.fromisoformat(last_run_str)
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
            gap = datetime.now(timezone.utc) - last_run
            if gap < timedelta(hours=1):
                logging.warning("上次运行在 %s 前（%s），如需重新运行请确认或加 --reset",
                                last_run.strftime("%H:%M:%S"), gap)
        except (ValueError, TypeError) as e:
            logging.warning("解析 last_run 失败: %s", e)

    if args.force:
        logging.info("--force: 清空 processed_set，重跑所有提案")
        processed_set = set()

    # ── Laya 健康检查 ────────────────────────────
    if not args.dry_run and not args.skip_laya_check:
        if not check_laya_health():
            logging.error("Laya 服务不可达，退出。使用 --dry-run 仅扫描，或 --skip-laya-check 强制跳过。")
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
        if should_skip(p, args.force, processed_set):
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

    import sup_paths as sp
    import registry_lib as rl

    if args.queue_path:
        queue_path = str(Path(args.queue_path))
    else:
        queue_path = sp.QUEUE

    os.makedirs(os.path.dirname(queue_path), exist_ok=True)

    verdict_history = load_verdict_history()
    covariate_menu = load_covariate_menu()
    logging.info("加载 %d 条历史裁决, covariate_menu: %s",
                 len(verdict_history), "有" if covariate_menu else "无")

    existing = set()
    dead = set()
    try:
        reg_snap = rl.load_snapshot(sp.REGISTRY)
        existing = set(reg_snap.keys())
        dead = rl.dead_variants(reg_snap)
        logging.info("REGISTRY 已有 %d 条，dead %d 条", len(existing), len(dead))
    except Exception as e:
        logging.warning("加载 REGISTRY 快照失败: %s", e)

    # P2-1: 并入 INPROGRESS/QUEUE 中的飞行中 vid，避免重复入队
    try:
        in_flight = rl.in_flight_ids(sp.QUEUE, sp.INPROGRESS)
        existing |= in_flight
        if in_flight:
            logging.info("并入 INPROGRESS/QUEUE 中 %d 个飞行中 vid", len(in_flight))
    except Exception as e:
        logging.warning("加载 INPROGRESS 失败: %s", e)

    # P2-4: max_points 从 cadence 配置读取
    max_points = _get_max_points()
    logging.info("aligned_max_points = %d (来自 cadence 配置)", max_points)

    start_time = time.monotonic()
    timeout_secs = args.timeout_min * 60

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_proposal, p, stats, verdict_history, covariate_menu,
                queue_path, dead, existing
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

            try:
                status_label = future.result()
            except Exception as e:
                logging.error("future 异常 %s: %s", proposal_path, e)
                status_label = "error"

            if status_label == "success":
                processed_set.add(proposal_path)

            if i % 10 == 0:
                state["processed"] = list(processed_set)
                state["stats"] = stats.snapshot()
                save_state(state)

            if i % 50 == 0 or i == len(to_process):
                snap = stats.snapshot()
                logging.info(
                    "进度: %d/%d (success=%d failed=%d enqueued=%d skipped=%d degraded=%d) elapsed=%.0fs",
                    i, len(to_process), snap["success"], snap["failed"],
                    snap["enqueued"], snap.get("skipped", 0), snap.get("degraded", 0), elapsed
                )

    elapsed = time.monotonic() - start_time
    snap = stats.snapshot()
    state["processed"] = list(processed_set)
    state["stats"] = snap
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["version"] = SCRIPT_VERSION
    save_state(state)

    logging.info("=" * 60)
    logging.info("完成: total=%d success=%d failed=%d enqueued=%d degraded=%d elapsed=%.0fs",
                 snap["total"], snap["success"], snap["failed"], snap["enqueued"],
                 snap.get("degraded", 0), elapsed)
    logging.info("状态文件: %s", STATE_FILE)
    logging.info("队列文件: %s", queue_path)
    logging.info("=" * 60)


if __name__ == "__main__":
    main()
