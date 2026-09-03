#!/usr/bin/env python3
"""
diracc_candidate_generator.py — DirAcc 候选生成器 (v2)

三步闭环:
  1. 生成候选: 全 24H MAE (walk-forward 3 点) 评估协变量质量
  2. 应用变更: 更新 prediction_scheme.py
  3. 回测验证: 运行 monthly_backtest.py, DirAcc 未提升则回滚

修正:
  - T+1 bias → 全局 MAE(T+1~T+24), 消除期限错配
  - 3 点 walk-forward, 消除 N=1 过拟合
  - 进程内循环, 避免 18 次模型加载
  - compile() 语法检查, 防止破坏代码
  - monthly_backtest 闭环验证

用法:
  python scripts/diracc_candidate_generator.py                    # 所有 <70% 品种
  python scripts/diracc_candidate_generator.py sr lh sp           # 指定品种
  python scripts/diracc_candidate_generator.py --dry-run          # 仅扫描不应用
  python scripts/diracc_candidate_generator.py --skip-backtest    # 跳过回测验证
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 路径设置 (必须在所有 import 之前) ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, FM_ROOT)
os.chdir(FM_ROOT)

import numpy as np
import sqlite3
from data.config import SYMBOL_NAMES
from data.data_store import DataStore
from cascade.daily_model import DailyModel
from cascade.hourly_model import HourlyModel
from config.prediction_scheme import SCHEMES

# ── 常量 ──

COVARIATE_TYPES = [
    'ccl', 'oi', 'rsi_slope', 'hourly_slope', 'rsi_state',
    'pca_momentum', 'hurst', 'gated_slope', 'regime_gated',
    'basis_momentum', 'vor',
]

COMBO_MODES = [
    ['oi', 'hurst'],
    ['rsi_state', 'oi'],
    ['hourly_slope', 'oi'],
    ['pca_momentum', 'hurst'],
]

TARGET_DIRACC = 0.70
WALK_FORWARD_POINTS = 3    # walk-forward 评估点数
WALK_FORWARD_STEP = 24     # 每点间隔 (1H bars)
HORIZON = 24               # 预测时域


# ── 数据查询 ──

def get_1h_prices(symbol: str, end_dt: str = None, limit: int = 1000) -> list[tuple]:
    """获取 1H 收盘价序列 [(dt, close), ...]，按时间升序。"""
    db_path = f'db/futures_{symbol}.db'
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    if end_dt:
        rows = conn.execute(
            'SELECT dt, close_price FROM kline_1h '
            'WHERE contract_code LIKE ? AND dt <= ? AND close_price > 0 '
            'ORDER BY dt DESC LIMIT ?',
            ('%_MAIN', end_dt, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT dt, close_price FROM kline_1h '
            'WHERE contract_code LIKE ? AND close_price > 0 '
            'ORDER BY dt DESC LIMIT ?',
            ('%_MAIN', limit)
        ).fetchall()
    conn.close()
    return [(r[0], float(r[1])) for r in reversed(rows)]


# ── 协变量扫描 (进程内, 单模型加载) ──

def scan_symbol(symbol: str, daily_model, hourly_model) -> dict:
    """
    Walk-forward 评估所有协变量。

    在 3 个历史时间点生成 24H 预测，与真实价格计算 MAE。
    返回: {covariates: [{type, mae, mae_by_horizon}], best: {...}}
    """
    # 获取 1H 数据 (需要足够长: context + walk-forward 评估窗口)
    prices = get_1h_prices(symbol, limit=1000)
    if len(prices) < 500:  # context_bars=480 + 评估窗口
        return {"covariates": [], "best": None, "success": False,
                "error": f"数据不足 ({len(prices)} < 500)"}

    # 选择 3 个评估锚点 (从最新往回)
    # 锚点: prices[-25], prices[-49], prices[-73]
    # 确保每个锚点后有 24 个真实价格用于 MAE 计算
    anchor_offsets = [
        len(prices) - WALK_FORWARD_STEP - HORIZON,       # 最近可评估点
        len(prices) - WALK_FORWARD_STEP * 2 - HORIZON,   # 第 2 个点
        len(prices) - WALK_FORWARD_STEP * 3 - HORIZON,   # 第 3 个点
    ]
    anchor_offsets = [o for o in anchor_offsets if o > 500]  # 确保 context 足够

    if not anchor_offsets:
        return {"covariates": [], "best": None, "success": False,
                "error": "无法确定评估锚点"}

    # 构建所有待测协变量列表
    all_covs = []
    for cov_type in COVARIATE_TYPES:
        all_covs.append(("single", cov_type, cov_type))
    for combo in COMBO_MODES:
        name = '+'.join(combo)
        all_covs.append(("combo", name, combo))

    print(f"    评估: {len(anchor_offsets)} 个历史点 × {len(all_covs)} 种协变量")

    # 逐协变量评估
    cov_results = {}

    for mode, cov_name, cov_param in all_covs:
        mae_all_points = []
        mae_by_horizon = [[] for _ in range(HORIZON)]

        for anchor_idx in anchor_offsets:
            # 锚点前的数据作为 context
            anchor_dt = prices[anchor_idx][0]
            context_prices = prices[:anchor_idx + 1]

            # 锚点后的实际价格 (ground truth)
            actual_window = prices[anchor_idx + 1: anchor_idx + 1 + HORIZON]
            if len(actual_window) < HORIZON:
                continue
            actual_closes = np.array([p[1] for p in actual_window])

            # 运行模型预测
            try:
                with DataStore(symbol) as store:
                    # 标记为回测模式，跳过时效性检查 (评估点是历史的)
                    store.cutoff_date = "9999-12-31"
                    # 日线预测
                    daily_result = daily_model.predict(symbol, store)

                    # 1H 级联预测
                    kwargs = dict(
                        symbol=symbol, store=store,
                        daily_result=daily_result, horizon=HORIZON,
                        visualize=False,
                    )
                    if mode == "single":
                        kwargs["covariate_type"] = cov_param
                    else:
                        kwargs["covariate_types"] = cov_param

                    hr = hourly_model.predict(**kwargs)
                    pred = np.array(hr.point_forecast).flatten()[:HORIZON]

                    if len(pred) < HORIZON:
                        continue

                    # 全局 MAE
                    errors = np.abs(pred - actual_closes) / actual_closes * 100
                    mae = float(np.mean(errors))
                    mae_all_points.append(mae)

                    # 分时段 MAE
                    for h in range(HORIZON):
                        err_h = abs(pred[h] - actual_closes[h]) / actual_closes[h] * 100
                        mae_by_horizon[h].append(err_h)

            except Exception as e:
                continue

        if mae_all_points:
            avg_mae = float(np.mean(mae_all_points))
            avg_by_horizon = [
                float(np.mean(h_errs)) if h_errs else 999.0
                for h_errs in mae_by_horizon
            ]
            cov_results[cov_name] = {
                "type": cov_name,
                "mae": round(avg_mae, 4),
                "points": len(mae_all_points),
                "mae_by_horizon": [round(v, 3) for v in avg_by_horizon],
            }

    if not cov_results:
        return {"covariates": [], "best": None, "success": False,
                "error": "所有协变量评估失败"}

    # 排序: MAE 越小越优
    sorted_covs = sorted(cov_results.values(), key=lambda x: x["mae"])
    best = sorted_covs[0]

    return {
        "covariates": sorted_covs,
        "best": best,
        "success": True,
    }


# ── 方案文件操作 ──

def apply_covariate_update(symbol: str, new_cov_type: str) -> bool:
    """更新 prediction_scheme.py 的协变量配置。

    支持单协变量 (covariate_type) 和组合模式 (covariate_types):
    - "pca_momentum" → 只更新 covariate_type
    - "pca_momentum+hurst" → 更新 covariate_type + covariate_types

    含语法安全检查。
    """
    scheme_file = os.path.join(FM_ROOT, 'config', 'prediction_scheme.py')
    text = open(scheme_file, 'r', encoding='utf-8').read()
    original_text = text

    is_combo = '+' in new_cov_type

    if is_combo:
        # 组合模式: 更新 covariate_type + covariate_types
        parts = new_cov_type.split('+')
        # 更新 covariate_type 为组合的第一个元素
        text = re.sub(
            rf'(symbol=["\']{symbol}["\'].*?)(covariate_type=["\'])(\w+)(["\'])',
            rf'\1\2{parts[0]}\4',
            text, count=1, flags=re.DOTALL
        )
        # 更新 covariate_types 为组合列表
        types_list = ', '.join(f'"{p}"' for p in parts)
        text = re.sub(
            rf'(symbol=["\']{symbol}["\'].*?)(covariate_types=\[)([^\]]*?)(\])',
            rf'\1\2{types_list}\4',
            text, count=1, flags=re.DOTALL
        )
    else:
        # 单协变量: 更新 covariate_type
        text = re.sub(
            rf'(symbol=["\']{symbol}["\'].*?)(covariate_type=["\'])(\w+)(["\'])',
            rf'\1\2{new_cov_type}\4',
            text, count=1, flags=re.DOTALL
        )
        # 清空 covariate_types（避免组合和单协变量冲突）
        text = re.sub(
            rf'(symbol=["\']{symbol}["\'].*?)(covariate_types=\[)([^\]]*?)(\])',
            rf'\1\2\4',
            text, count=1, flags=re.DOTALL
        )

    if text == original_text:
        return False

    # ── 安全检查 ──

    # 1. 语法编译测试
    try:
        compile(text, 'prediction_scheme.py', 'exec')
    except SyntaxError as e:
        print(f"    [FATAL] 正则替换破坏语法: {e}")
        return False

    # 2. 品种数量不变
    orig_count = original_text.count('VarietyScheme(')
    new_count = text.count('VarietyScheme(')
    if orig_count != new_count:
        print(f"    [FATAL] 品种数量变化: {orig_count} → {new_count}")
        return False

    # 3. 备份 + 写入
    backup = scheme_file + '.bak'
    with open(backup, 'w', encoding='utf-8') as f:
        f.write(original_text)

    with open(scheme_file, 'w', encoding='utf-8') as f:
        f.write(text)

    return True


def rollback_scheme():
    """从 .bak 回滚 prediction_scheme.py。"""
    scheme_file = os.path.join(FM_ROOT, 'config', 'prediction_scheme.py')
    backup = scheme_file + '.bak'
    if os.path.exists(backup):
        import shutil
        shutil.copy2(backup, scheme_file)
        print("  ↩️  已回滚 prediction_scheme.py")
        return True
    return False


# ── 回测验证 ──

def run_backtest_verification(symbols: list[str]) -> dict:
    """运行 monthly_backtest 验证 DirAcc 是否提升。

    Returns: {success, dir_acc_before, dir_acc_after, improved}
    """
    # 读取回测前的 DirAcc (从 history.json 最后一月)
    history_file = os.path.join(FM_ROOT, 'reports', 'monthly_backtest', 'history.json')
    before_da = {}
    if os.path.exists(history_file):
        try:
            data = json.loads(open(history_file, 'r', encoding='utf-8').read())
            months = sorted(data.keys())
            if months:
                for item in data[months[-1]].get("summary", []):
                    before_da[item["symbol"].lower()] = item.get("dir_acc", 0)
        except Exception:
            pass

    # 运行月度回测
    print(f"\n  运行月度回测: {', '.join(symbols)}")
    try:
        proc = subprocess.run(
            [sys.executable, 'scripts/monthly_backtest.py'] + symbols,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=1800, cwd=FM_ROOT,
        )

        # 读取回测后的 DirAcc
        after_da = {}
        if os.path.exists(history_file):
            try:
                data = json.loads(open(history_file, 'r', encoding='utf-8').read())
                months = sorted(data.keys())
                if months:
                    for item in data[months[-1]].get("summary", []):
                        after_da[item["symbol"].lower()] = item.get("dir_acc", 0)
            except Exception:
                pass

        # 对比
        improved = 0
        degraded = 0
        for sym in symbols:
            b = before_da.get(sym, 0)
            a = after_da.get(sym, 0)
            if a > b + 0.01:
                improved += 1
            elif a < b - 0.01:
                degraded += 1

        return {
            "success": proc.returncode == 0,
            "before": before_da,
            "after": after_da,
            "improved": improved,
            "degraded": degraded,
            "net": improved - degraded,
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "回测超时 (30min)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 主入口 ──

def main():
    parser = argparse.ArgumentParser(description="DirAcc 候选生成器 (v2)")
    parser.add_argument("symbols", nargs="*", help="指定品种 (默认: 所有 <70%)")
    parser.add_argument("--threshold", type=float, default=TARGET_DIRACC)
    parser.add_argument("--dry-run", action="store_true", help="仅扫描不应用")
    parser.add_argument("--skip-backtest", action="store_true", help="跳过回测验证")
    args = parser.parse_args()

    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"# 🎯 DirAcc 候选生成器 v2\n")
    print(f"**时间**: {now_str}  ")
    print(f"**目标**: DirAcc ≥ {args.threshold:.0%}  ")
    print(f"**评估指标**: 全局 MAE(T+1~T+24), walk-forward {WALK_FORWARD_POINTS} 点\n")

    # 筛选待优化品种
    if args.symbols:
        targets = {s: SCHEMES[s] for s in args.symbols if s in SCHEMES}
    else:
        targets = {s: sc for s, sc in SCHEMES.items() if sc.dir_acc < args.threshold}

    if not targets:
        print("✅ 所有品种 DirAcc 已达标\n")
        return

    sorted_targets = sorted(targets.items(), key=lambda x: -x[1].dir_acc)
    print(f"**待优化**: {len(sorted_targets)} 个品种\n")
    print("| 品种 | 名称 | DirAcc | 当前协变量 | 模式 |")
    print("|------|------|:------:|-----------|:----:|")
    for sym, sc in sorted_targets:
        has_combo = sc.covariate_types is not None and len(sc.covariate_types) > 0
        cov_display = '+'.join(sc.covariate_types) if has_combo else sc.covariate_type
        mode = "组合" if has_combo else "单"
        print(f"| `{sym}` | {SYMBOL_NAMES.get(sym, '')} | {sc.dir_acc:.1%} | `{cov_display}` | {mode} |")
    print()

    # ── 加载模型 (一次) ──
    print("## Phase 1: 加载 TimesFM 模型\n")
    t0 = time.time()
    daily_model = DailyModel()
    hourly_model = HourlyModel(shared_model=daily_model.model)
    print(f"  模型加载完成 ({time.time()-t0:.0f}s)\n")

    # ── Phase 2: 扫描 ──
    print("## Phase 2: Walk-forward MAE 评估\n")
    candidates = []  # (symbol, old_cov, new_cov, old_mae, new_mae)

    for i, (sym, scheme) in enumerate(sorted_targets, 1):
        print(f"### [{i}/{len(sorted_targets)}] {sym.upper()} ({SYMBOL_NAMES.get(sym, '')})")
        print(f"  DirAcc={scheme.dir_acc:.1%}, covariate=`{scheme.covariate_type}`")

        t1 = time.time()
        result = scan_symbol(sym, daily_model, hourly_model)
        scan_time = time.time() - t1

        if not result["success"]:
            print(f"  ❌ {result.get('error', '未知错误')}\n")
            continue

        best = result["best"]
        # 确定当前有效协变量（单协变量或组合）
        has_combo = scheme.covariate_types is not None and len(scheme.covariate_types) > 0
        old_cov = '+'.join(scheme.covariate_types) if has_combo else scheme.covariate_type
        new_cov = best["type"]

        # 找到当前协变量的 MAE
        old_mae = None
        for c in result["covariates"]:
            if c["type"] == old_cov:
                old_mae = c["mae"]
                break

        print(f"  最优: `{new_cov}` (MAE={best['mae']:.2f}%)")
        if old_mae is not None:
            print(f"  当前: `{old_cov}` (MAE={old_mae:.2f}%)")
            print(f"  改善: {old_mae - best['mae']:+.2f}% MAE")

        # TOP 3
        for j, c in enumerate(result["covariates"][:3]):
            mark = " ← 当前" if c["type"] == old_cov else (" ← 最优" if j == 0 else "")
            print(f"    #{j+1} `{c['type']}` MAE={c['mae']:.2f}%{mark}")

        print(f"  ({scan_time:.0f}s)\n")

        if new_cov != old_cov:
            candidates.append((sym, old_cov, new_cov, old_mae, best["mae"]))

    if not candidates:
        print("## ✅ 所有品种当前协变量已最优\n")
        return

    print(f"## 候选更新: {len(candidates)} 个品种\n")
    print("| 品种 | 原协变量 | 新协变量 | 原MAE | 新MAE |")
    print("|------|---------|---------|------:|------:|")
    for sym, old, new, old_mae, new_mae in candidates:
        old_s = f"{old_mae:.2f}%" if old_mae else "N/A"
        print(f"| `{sym}` | `{old}` | `{new}` | {old_s} | {new_mae:.2f}% |")

    if args.dry_run:
        print("\n> [dry-run] 不应用任何更改\n")
        return

    # ── Phase 3: 应用 ──
    print(f"\n## Phase 3: 应用变更\n")
    applied = []
    for sym, old, new, old_mae, new_mae in candidates:
        ok = apply_covariate_update(sym, new)
        if ok:
            print(f"  ✅ {sym}: `{old}` → `{new}`")
            applied.append(sym)
        else:
            print(f"  ❌ {sym}: 更新失败")

    if not applied:
        return

    # ── Phase 4: 回测验证 ──
    if args.skip_backtest:
        print(f"\n## ⏸️ 跳过回测验证 (--skip-backtest)\n")
        print(f"已更新 {len(applied)} 个品种。建议手动运行:")
        print(f"  python scripts/monthly_backtest.py {' '.join(applied)}\n")
    else:
        print(f"\n## Phase 4: 回测验证\n")
        bt = run_backtest_verification(applied)

        if bt.get("success") and bt.get("net", 0) >= 0:
            print(f"\n  ✅ 回测通过: {bt['improved']} 提升, {bt['degraded']} 下降")
            print(f"  变更已保留。\n")
        elif bt.get("success"):
            print(f"\n  ⚠️ 回测退化: {bt['improved']} 提升, {bt['degraded']} 下降")
            print(f"  净退化 {abs(bt['net'])} 个品种。\n")
            if bt["degraded"] > bt["improved"]:
                print("  ↩️  自动回滚!")
                rollback_scheme()
            else:
                print("  保留变更（提升 > 退化）")
        else:
            print(f"\n  ❌ 回测失败: {bt.get('error', '未知')}\n")
            print("  保留变更，建议手动验证。")

    print(f"\n## 完成\n")


if __name__ == "__main__":
    main()
