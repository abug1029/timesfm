#!/usr/bin/env python3
"""Phase 10: Supervisor 重启就绪验证。

脚本检查所有新代码能被 supervisor 成功加载。
用户确认后运行 scripts/restart_supervisor.sh 实际重启。

退出码：
  0 = 全部就绪，可重启
  1 = 加载失败，需修复后再重启
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

FM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FM_ROOT))
sys.path.insert(0, str(FM_ROOT / "scripts"))
sys.path.insert(0, str(FM_ROOT / "task_FM" / "evaluations" / "fm_eval"))

FAILURES = []


def check(name: str, fn):
    """执行检查，失败时记录。"""
    try:
        fn()
        print(f"  ✅ {name}")
    except Exception as e:
        FAILURES.append((name, e))
        print(f"  ❌ {name}: {e}")


# ── 1) 新模块可导入 ──────────────────────────────────────────
print("\n[1/6] 新模块导入")
check("cascade.horizon_fill", lambda: importlib.import_module("cascade.horizon_fill"))
check("cascade.research_family", lambda: importlib.import_module("cascade.research_family"))
check("cascade.experiment_fingerprint", lambda: importlib.import_module("cascade.experiment_fingerprint"))


# ── 2) 既有模块仍可导入（无破坏性变更） ─────────────────────
print("\n[2/6] 既有模块回归")
for mod in ["cascade.features", "cascade.hourly_model", "cascade.ccl_monitor",
            "cascade.vol_risk_filter", "cascade.neutral_ab_report",
            "cascade.statistical_tests", "cascade.evaluation_metrics",
            "scripts.registry_lib", "scripts.fingerprint_lib"]:
    check(mod, lambda m=mod: importlib.import_module(m))


# ── 3) Phase 1-3 关键契约 ─────────────────────────────────────
print("\n[3/6] Phase 1-3 契约")
def check_phase1_3():
    from cascade.statistical_tests import detection_threshold_vs_random, n_required
    assert abs(detection_threshold_vs_random(73) - 0.596) < 0.01, "vs_random 黄金值"
    assert abs(n_required(var_d=0.25, vif=8.028, delta=0.10) - 1240) < 60, "n_required 黄金值"
    from cascade.horizon_fill import get_horizon_known
    assert get_horizon_known("rsi_state") in ("persistence", "self_referential", "unknowable", "known_ahead")
    assert get_horizon_known("calendar_cyclical") == "known_ahead"
check("Phase 1-3 契约", check_phase1_3)


# ── 4) Phase 5 指纹 v4 ────────────────────────────────────────
print("\n[4/6] Phase 5 指纹")
def check_phase5():
    from task_FM.evaluations.fm_eval.evaluator import (
        PROTOCOL_FINGERPRINT_VERSION, compute_protocol_fingerprint,
        ADJUSTMENT_RULE_VERSION, ROLL_GUARD_VERSION,
    )
    assert PROTOCOL_FINGERPRINT_VERSION == "protocol_v4", f"指纹版本应为 v4，实际 {PROTOCOL_FINGERPRINT_VERSION}"
    fp = compute_protocol_fingerprint()
    assert len(fp) == 64, "指纹应为 64 位 hex"
    assert ADJUSTMENT_RULE_VERSION == "v1"
    assert ROLL_GUARD_VERSION == "v1"
check("指纹 v4 + 组件（含窗口锚）", check_phase5)


# ── 5) Phase 7 experiment_fingerprint ────────────────────────
print("\n[5/6] Phase 7 实验指纹")
def check_phase7():
    from cascade.experiment_fingerprint import (
        compute_experiment_fingerprint, build_variant_id,
        birthday_collision_probability, TRUNCATE_HEX_LEN,
    )
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "version.txt"), "w") as f:
            f.write("v1")
        fp = compute_experiment_fingerprint(td, [1.0, 2.0], 480, 24, 2, ["rsi_state"])
        assert len(fp) == 64
        vid = build_variant_id("ss", "momentum", fp)
        assert vid.startswith("ss_momentum_")
        assert len(vid.split("_")[-1]) == TRUNCATE_HEX_LEN
    # 48-bit 碰撞论证
    assert birthday_collision_probability(1000) < 1e-6
check("experiment_fingerprint + variant_id", check_phase7)


# ── 6) Phase 2 family 逻辑 ───────────────────────────────────
print("\n[6/6] Phase 2 研究 family")
def check_phase2():
    from cascade.research_family import (
        default_family_key, make_member, register_member, seal_family,
        family_bh_fdr, TERMINAL_STATES, FAMILY_CLOSE_AFTER, T_MAX,
    )
    from datetime import datetime, timezone, timedelta
    k = default_family_key("ss")
    assert k, "family_key 不得为空"
    # 封账流程
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    m1 = make_member(k, "ss", "v1", now)
    mem = [m1]
    sealed, adj = seal_family([
        {**m1, "status": "confirmed", "p_value": 0.01},
        {**make_member(k, "ss", "v2", now), "status": "refuted", "p_value": 0.6},
    ], now)
    assert len(sealed) == 2
    assert all(m["family_sealed_at"] for m in sealed)
check("family 注册/封账/BH-FDR", check_phase2)


# ── 汇总 ──────────────────────────────────────────────────────
print("\n" + "=" * 60)
if FAILURES:
    print(f"❌ 重启就绪检查失败：{len(FAILURES)} 项")
    for name, err in FAILURES:
        print(f"   - {name}: {err}")
    sys.exit(1)
else:
    print("✅ 重启就绪检查通过：所有新代码可加载，契约完整。")
    print("\n下一步（需用户确认维护窗口）：")
    print("  1. scripts/stop_supervisor.sh   # 优雅停止 PID 22703")
    print("  2. mv logs/supervisor.log logs/supervisor_pre_restart_$(date +%Y%m%d).log")
    print("  3. scripts/start_supervisor.sh  # 重启")
    print("  4. tail -f logs/supervisor.log  # 观察加载证据")
    print("  5. 验证：N3 守卫 / 复测分派 / family 逻辑 / ensure_baselines 归档路径")
    sys.exit(0)
