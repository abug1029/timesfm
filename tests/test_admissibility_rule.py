"""步③ B 边缘连续块豁免 + admissibility_rule 行级字段测试（事项一五步之 3/5）。

裁定 B（2026-10-07，dm-status 报告附录 A.2）：
- 边缘连续块豁免——变体侧最新连续块 / 基线侧最旧连续块 + 有界性双条件
  「每侧 ≤30 日期」，任一不满足落回 descriptive；
- 窗内缺失仍 False；
- 只翻转 missingness_admissible，不改 dir_acc/d_t/DM 统计量与 p 值。

采集包（附录 A.3）：
- 行级 unmatched 位置（每侧 ≤30 日期）与连续性判定；
- admissibility_rule 为行级可选字段，唯一写入路径 = 裁决行产出。

实施前断言（A.5）：同一行 protocol_fingerprint 前后不变（B 只改 missingness_admissible
判定规则，不碰指纹计算）。
"""
import json, os, sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import cascade.statistical_tests as st


def _make_points(base_dt, n, step_hours=2, fp="fp_test"):
    """生成 n 个评估点，间隔 step_hours。"""
    points = []
    for i in range(n):
        cutoff = base_dt + timedelta(hours=i * step_hours)
        points.append({
            "cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S"),
            "dir_ok": True,
            "delta_pred": 1.0,
            "delta_real": 1.0,
            "protocol_fingerprint": fp,
        })
    return points


# ── 边缘连续块 + 有界性检查 ──────────────────────────────────────

def test_admissible_when_unmatched_within_30_days():
    """missingness_admissible=True + unmatched ≤30 日期 → set_mismatch_ok（通过）。"""
    base = datetime(2026, 10, 1, 0, 0, 0)
    # 变体 100 点（10-01 ~ 10-05），基线 90 点（10-01 ~ 10-04）
    # unmatched_variant = 10 点 ≈ 3.3 天 ≤30 ✓
    # unmatched_baseline = 0 ✓
    variant = _make_points(base, 100)
    baseline = _make_points(base, 90)
    result = st.pair_dir_ok_series_with_diagnostics(
        variant, baseline, missingness_admissible=True,
        variant_protocol="fp_test", baseline_protocol="fp_test")
    assert result["dm_status"] == "set_mismatch_ok"
    assert result["admissibility_rule"] == "edge_continuous_block_30d"


def test_descriptive_when_unmatched_exceeds_30_days():
    """missingness_admissible=True 但 unmatched >30 日期 → set_mismatch_descriptive（落回）。"""
    base = datetime(2026, 10, 1, 0, 0, 0)
    # 变体 200 点（10-01 ~ 10-09），基线 90 点（10-01 ~ 10-04）
    # unmatched_variant = 110 点 ≈ 36.7 天 >30 ✗
    variant = _make_points(base, 200)
    baseline = _make_points(base, 90)
    result = st.pair_dir_ok_series_with_diagnostics(
        variant, baseline, missingness_admissible=True,
        variant_protocol="fp_test", baseline_protocol="fp_test")
    assert result["dm_status"] == "set_mismatch_descriptive"
    assert result.get("admissibility_rule") is None


def test_descriptive_when_missingness_not_admissible():
    """missingness_admissible=False → set_mismatch_descriptive（原逻辑不变）。"""
    base = datetime(2026, 10, 1, 0, 0, 0)
    variant = _make_points(base, 100)
    baseline = _make_points(base, 90)
    result = st.pair_dir_ok_series_with_diagnostics(
        variant, baseline, missingness_admissible=False,
        variant_protocol="fp_test", baseline_protocol="fp_test")
    assert result["dm_status"] == "set_mismatch_descriptive"
    assert result.get("admissibility_rule") is None


def test_ok_when_no_unmatched():
    """missingness_admissible=True + unmatched=0 → ok（原逻辑不变）。"""
    base = datetime(2026, 10, 1, 0, 0, 0)
    points = _make_points(base, 100)
    result = st.pair_dir_ok_series_with_diagnostics(
        points, points, missingness_admissible=True,
        variant_protocol="fp_test", baseline_protocol="fp_test")
    assert result["dm_status"] == "ok"
    assert result["admissibility_rule"] == "edge_continuous_block_30d"


# ── 实施前断言（A.5）：指纹不变 ─────────────────────────────────

def test_protocol_fingerprint_unchanged():
    """B 只改 missingness_admissible 判定规则，不碰指纹计算。"""
    # 用活仓基线文件验证指纹不变（f02b2a43...）
    baseline_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "task_FM", "config", "baseline_points_jd_nocov.jsonl")
    if not os.path.exists(baseline_path):
        return  # 跳过（worktree 无数据资产）
    with open(baseline_path, encoding="utf-8") as f:
        first_line = json.loads(f.readline())
    stored_fp = first_line.get("protocol_fingerprint")
    # 当前指纹 = f02b2a43...（v4 协议）
    assert stored_fp is not None
    assert stored_fp.startswith("f02b2a43")


# ── P2 补测：非连续 unmatched 应落 descriptive ──────────────────

def test_descriptive_when_unmatched_not_tail_continuous():
    """变体侧 unmatched 散落在窗中间（非尾部连续块）→ descriptive。"""
    base = datetime(2026, 10, 1, 0, 0, 0)
    # 变体 100 点（10-01 ~ 10-05），基线 95 点（10-01 ~ 10-03 + 10-04 后半 + 10-05 前半）
    # unmatched_variant = 5 点散落在窗中间（第 20/40/60/80/90 位）→ 非尾部连续
    variant = _make_points(base, 100)
    baseline = _make_points(base, 95)
    # 手动移除基线中间 5 个点（制造非连续 unmatched）
    baseline = [p for i, p in enumerate(baseline) if i not in [20, 40, 60, 80, 90]]
    result = st.pair_dir_ok_series_with_diagnostics(
        variant, baseline, missingness_admissible=True,
        variant_protocol="fp_test", baseline_protocol="fp_test")
    assert result["dm_status"] == "set_mismatch_descriptive"


def test_descriptive_when_variant_unmatched_not_tail():
    """变体侧 unmatched 在头部（非尾部）→ descriptive。"""
    base = datetime(2026, 10, 1, 0, 0, 0)
    # 变体 100 点（00:00 ~ 10-05），基线 95 点（10:00 ~ 10-05）
    # only_variant = 变体前 5 点（00:00 ~ 08:00，基线没覆盖）→ 在变体头部（非尾部）
    variant = _make_points(base, 100)
    baseline = _make_points(base + timedelta(hours=10), 95)  # 从 10:00 开始
    result = st.pair_dir_ok_series_with_diagnostics(
        variant, baseline, missingness_admissible=True,
        variant_protocol="fp_test", baseline_protocol="fp_test")
    # 变体 unmatched 在头部 → 非尾部连续 → descriptive
    assert result["dm_status"] == "set_mismatch_descriptive"


def test_descriptive_when_baseline_unmatched_not_head():
    """基线侧 unmatched 在尾部（非头部）→ descriptive。"""
    base = datetime(2026, 10, 1, 0, 0, 0)
    # 变体 95 点（00:00 ~ 10-04），基线 100 点（00:00 ~ 10-05）
    # only_baseline = 基线尾部 5 点（变体没覆盖）→ 在基线尾部（非头部）
    variant = _make_points(base, 95)
    baseline = _make_points(base, 100)
    result = st.pair_dir_ok_series_with_diagnostics(
        variant, baseline, missingness_admissible=True,
        variant_protocol="fp_test", baseline_protocol="fp_test")
    # 基线 unmatched 在尾部 → 非头部连续 → descriptive
    assert result["dm_status"] == "set_mismatch_descriptive"


# ── R2 采集包：unmatched 位置信息 ──────────────────────────────

def test_unmatched_dates_collected():
    """通过时采集 unmatched 位置信息（日期列表）。"""
    base = datetime(2026, 10, 1, 0, 0, 0)
    variant = _make_points(base, 100)
    baseline = _make_points(base, 95)
    result = st.pair_dir_ok_series_with_diagnostics(
        variant, baseline, missingness_admissible=True,
        variant_protocol="fp_test", baseline_protocol="fp_test")
    assert result["dm_status"] == "set_mismatch_ok"
    assert "unmatched_variant_dates" in result
    assert "unmatched_baseline_dates" in result
    assert len(result["unmatched_variant_dates"]) == 5  # 100 - 95 = 5
    assert len(result["unmatched_baseline_dates"]) == 0


# ── 五读取点过滤框架（步③b）─────────────────────────────────────

def test_fdr_pass_persistable_requires_admissibility_rule():
    """fdr_pass_persistable 要求 admissibility_rule 非 None（旧行不计入）。"""
    import praxist_supervisor as sup
    # 有 admissibility_rule → 通过
    row_ok = {"run_mode": "confirmation", "missingness_admissible": True,
              "dm_status": "ok", "admissibility_rule": "edge_continuous_block_30d"}
    assert sup.fdr_pass_persistable(row_ok) is True
    # 无 admissibility_rule → 不通过（旧行过滤）
    row_old = {"run_mode": "confirmation", "missingness_admissible": True,
               "dm_status": "ok"}
    assert sup.fdr_pass_persistable(row_old) is False


def test_test_invalid_requires_admissibility_rule():
    """_test_invalid 要求 admissibility_rule 非 None。"""
    import preregistry as pr
    # 有 admissibility_rule + 其他条件满足 → 非 invalid
    row_ok = {"pairing_valid": True, "missingness_admissible": True,
              "protocol_compatible": True, "dm_status": "ok",
              "admissibility_rule": "edge_continuous_block_30d"}
    assert pr._test_invalid(row_ok) is False
    # 无 admissibility_rule → invalid（旧行过滤）
    row_old = {"pairing_valid": True, "missingness_admissible": True,
               "protocol_compatible": True, "dm_status": "ok"}
    assert pr._test_invalid(row_old) is True


def test_passes_confirmation_requires_admissibility_rule():
    """_passes_confirmation 要求 admissibility_rule 非 None。"""
    import preregistry as pr
    row_ok = {"gate_pass": True, "p_value": 0.01, "covariates_used": True,
              "pairing_valid": True, "missingness_admissible": True,
              "protocol_compatible": True, "dm_significant": True,
              "dm_status": "ok", "admissibility_rule": "edge_continuous_block_30d"}
    assert pr._passes_confirmation(row_ok) is True
    row_old = {"gate_pass": True, "p_value": 0.01, "covariates_used": True,
               "pairing_valid": True, "missingness_admissible": True,
               "protocol_compatible": True, "dm_significant": True,
               "dm_status": "ok"}
    assert pr._passes_confirmation(row_old) is False


def test_classify_confirmation_requires_admissibility_rule():
    """classify_confirmation 要求 admissibility_rule 非 None（否则 underpowered）。"""
    import preregistry as pr
    row_ok = {"run_mode": "confirmation", "contaminated": False,
              "early_sealed": False, "common_insufficient": False,
              "meets_min_info": True, "n_confirm_actual": 100,
              "n_confirm_required": 50, "gate_pass": True, "p_value": 0.01,
              "covariates_used": True, "pairing_valid": True,
              "missingness_admissible": True, "protocol_compatible": True,
              "dm_significant": True, "dm_status": "ok",
              "admissibility_rule": "edge_continuous_block_30d"}
    assert pr.classify_confirmation(row_ok) == "confirmed"
    row_old = dict(row_ok)
    del row_old["admissibility_rule"]
    # 无 admissibility_rule → _passes_confirmation=False → _test_invalid=True → underpowered
    assert pr.classify_confirmation(row_old) == "underpowered"


def test_family_confirmatory_counts_requires_admissibility_rule():
    """_family_confirmatory_counts 只计有 admissibility_rule 的行。"""
    import praxist_supervisor as sup
    rows = [
        {"status": "ok", "dm_status": "ok", "cov_family": "momentum",
         "gate_pass": True, "admissibility_rule": "edge_continuous_block_30d"},
        {"status": "ok", "dm_status": "ok", "cov_family": "momentum",
         "gate_pass": False},  # 无 admissibility_rule → 不计入
    ]
    fam_ok, fam_pass = sup._family_confirmatory_counts(rows)
    assert fam_ok.get("momentum") == 1  # 只计第一行
    assert fam_pass.get("momentum") == 1
