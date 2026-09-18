"""FM_a v23 评估器错误路径 + 边界校验测试 (2026-09-17)

目标: task_FM/evaluations/fm_eval/evaluator.py 的错误处理与边界行为:
- validate_candidate: 非法输入拒绝 / 类型边界 / 归档协变量
- load_baseline_points: 空文件 / 空行 / 畸形 JSON 的 fail-fast 行为 (2026-09-17 修复)
- map_summary: 缺字段默认值 / 非法值回退 / NaN 传播
- gate: 精确边界 (n=350, n_eff=50, dir_acc=0.52) / NaN-inf / 自适应门下限与上限
- effective_sample_size: 重叠窗口 ESS 公式边界 (step>=horizon, step=0, rho 极值)
- build_summary: DM 配对样本 99/100 边界 / 统计模块异常吞掉 / None 列表
- pair_dir_ok_series: 重复时间戳 / 非法时间戳 / 混合格式 (经 evaluator 引用)
- diebold_mariano_p: 零差分序列 / 劣于基线 / 样本不足 / 长度不匹配

约定: 只断言行为, 不修改生产代码。标 [PIN] 的测试固化当前实现行为——
若生产代码后续修复, 应同步更新对应断言 (详见任务报告中的疑似 bug 清单)。
2026-09-17: 审计清单 bug #1-#7 已修复, 对应原 [PIN] 断言已同步为修复后行为,
原 [PIN] 标记移除改为普通回归测试; bug #8 (负 rho 无上限帽) 暂缓待产品决策。
"""
import importlib.util
import json
import math
import os
import tempfile

import pytest

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "fm_evaluator_errpath",
    os.path.join(FM_ROOT, "task_FM", "evaluations", "fm_eval", "evaluator.py"))
fm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm)


# ══════════════════ validate_candidate ══════════════════

class TestValidateCandidateErrors:
    """validate_candidate 是平台调度的第一道闸, 拒绝劣质候选保护算力."""

    @pytest.mark.parametrize("bad", [None, [], "m", 42, ["m"]])
    def test_non_mapping_rejected(self, bad):
        # 候选 JSON 若被平台误传为标量/列表, 必须拒绝而非崩溃或放行
        ok, why = fm.validate_candidate(bad)
        assert ok is False
        assert "mapping" in why

    def test_symbol_case_insensitive_accepted(self):
        # run.py 对 symbol 做 .upper() 回测, 校验层必须同样大小写不敏感
        ok, why = fm.validate_candidate({"symbol": "M", "cov_override": "rsi_state"})
        assert ok is True

    @pytest.mark.parametrize("bad_symbol", ["", "xx", "xyz", 42, None])
    def test_unknown_symbol_rejected(self, bad_symbol):
        # 符号清单是硬约束: 不在 21 品种白名单的候选不得进入回测
        ok, _ = fm.validate_candidate({"symbol": bad_symbol, "cov_override": "rsi_state"})
        assert ok is False

    def test_archived_covariate_rejected_before_valid_pool(self, monkeypatch):
        # 协变量同时存在于归档表与 active 池: 只有拒绝理由是 "archived" 而非
        # "不在预注册清单", 才真正钉住归档检查先于 VALID 池检查的顺序语义
        monkeypatch.setattr(fm, "ARCHIVED_COVARIATES", {"dual_status_cov": "测试归档原因"})
        monkeypatch.setattr(fm, "VALID_COVARIATES",
                            fm.VALID_COVARIATES | {"dual_status_cov"})
        ok, why = fm.validate_candidate({"symbol": "m", "cov_override": "dual_status_cov"})
        assert ok is False
        assert "archived" in why

    def test_missing_cov_override_rejected(self):
        # cov_override 缺失 (None 不在预注册清单) → 拒绝, 防静默回退到无协变量基线
        ok, _ = fm.validate_candidate({"symbol": "m"})
        assert ok is False

    def test_invalid_stage_rejected(self):
        # stage 决定样本预算与硬门可达性, 未知 stage 不得静默回退
        ok, _ = fm.validate_candidate({"symbol": "m", "cov_override": "rsi_state",
                                       "stage": "half_aligned"})
        assert ok is False

    @pytest.mark.parametrize("mp,stage", [
        (0, "diagnostic"), (7, "diagnostic"),          # diagnostic 区间 1..6
        (349, "aligned")  , (601, "aligned"),          # aligned 区间 350..600
        ("6", "diagnostic"), (6.5, "diagnostic"),      # 类型: 字符串/浮点
    ])
    def test_max_points_out_of_range_or_wrong_type_rejected(self, mp, stage):
        # max_points 决定 n 预算; 非法值会让 aligned 候选跑不出 n>=350 的硬门样本
        ok, _ = fm.validate_candidate({"symbol": "m", "cov_override": "rsi_state",
                                       "stage": stage, "max_points": mp})
        assert ok is False

    @pytest.mark.parametrize("mp,stage", [(1, "diagnostic"), (6, "diagnostic"),
                                          (350, "aligned"), (600, "aligned")])
    def test_max_points_exact_bounds_accepted(self, mp, stage):
        # 区间端点必须双向闭区间: 预注册候选常压在端点上
        ok, why = fm.validate_candidate({"symbol": "m", "cov_override": "rsi_state",
                                         "stage": stage, "max_points": mp})
        assert ok is True

    @pytest.mark.parametrize("stage,default_mp", [("diagnostic", 6), ("aligned", 400)])
    def test_default_max_points_valid_per_stage(self, stage, default_mp):
        # 缺省 max_points 的候选走 stage 默认值, 必须落在各自区间内
        ok, _ = fm.validate_candidate({"symbol": "m", "cov_override": "rsi_state",
                                       "stage": stage})
        assert ok is True

    def test_max_points_bool_rejected(self):
        # 2026-09-17 修复审计 bug #6: bool 是 int 子类, max_points=True 不再被当作 1 接受
        ok, _ = fm.validate_candidate({"symbol": "m", "cov_override": "rsi_state",
                                       "stage": "diagnostic", "max_points": True})
        assert ok is False



# ══════════════════ load_baseline_points ══════════════════

class TestLoadBaselinePointsErrors:
    """基线点文件是 DM 检验的对照序列, 损坏文件的行为决定统计证据的可信度."""

    def test_empty_file_returns_empty_list(self):
        # 空文件 → 空列表: aligned 候选不会得到 p_value, 被上层 >=100 防护拦截
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "baseline_points_m.jsonl"), "w").close()
            assert fm.load_baseline_points("m", root=tmp) == []

    def test_blank_lines_skipped(self):
        # 尾部空行/连续空行是编辑器常见产物, 不应计入点数
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "baseline_points_m.jsonl")
            with open(path, "w") as f:
                f.write("\n")
                f.write(json.dumps({"cutoff": "2024-06-15 09:00:00", "dir_ok": True}) + "\n")
                f.write("   \n")
            result = fm.load_baseline_points("m", root=tmp)
            assert len(result) == 1

    def test_malformed_json_fails_fast(self):
        # 2026-09-17 修复审计 bug #3: 中途坏行不再 fail-open 静默截断, 改为 fail-fast
        # 抛 ValueError (带行号) — DM 配对样本无声缩水比整批失败更危险
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "baseline_points_m.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps({"cutoff": "2024-06-15 09:00:00", "dir_ok": True}) + "\n")
                f.write("{not valid json\n")
                f.write(json.dumps({"cutoff": "2024-06-15 11:00:00", "dir_ok": False}) + "\n")
            with pytest.raises(ValueError, match="第 2 行"):
                fm.load_baseline_points("m", root=tmp)


# ══════════════════ map_summary ══════════════════

class TestMapSummaryDefaults:
    """map_summary 是慢环 summarize 输出到 v23 指标命名的适配层, 缺字段默认值决定下游门控输入."""

    def test_empty_dict_all_defaults(self):
        # 完全空 summary → 中性默认: dir_acc=0.5 (掷硬币), path_corr=None (不可算)
        m = fm.map_summary({})
        assert m["n"] == 0
        assert m["n_eff"] == 0
        assert m["dir_acc"] == 0.5
        assert m["endpoint_mape"] == 0.0
        assert m["endpoint_bias_pct"] == 0.0
        assert m["path_corr"] is None
        assert m["weighted_dir_acc"] == 0.5
        assert m["mae"] == 0.0
        assert m["mape"] == 0.0
        assert m["decay"] == 1.0

    def test_n_eff_falls_back_to_n(self):
        # 旧 summarize 输出无 n_eff → 回退到名义 n (无重叠修正, 保守性由上层 ESS 兜底)
        assert fm.map_summary({"n": 400})["n_eff"] == 400

    @pytest.mark.parametrize("key,default", [
        ("dir_acc", 0.5), ("endpoint_mape", 0.0), ("endpoint_bias_pct", 0.0),
        ("weighted_dir_acc", 0.5), ("mae", 0.0), ("mape", 0.0), ("decay", 1.0),
    ])
    def test_non_numeric_string_falls_back_to_default(self, key, default):
        # 上游序列化损坏 (值变非数字字符串) 不应让毒值进入门控
        m = fm.map_summary({key: "not-a-number"})
        assert m[key] == default

    def test_path_corr_non_numeric_becomes_none(self):
        # path_corr 不可算时语义是 None (诊断级缺失), 不是 0 (完美无关)
        assert fm.map_summary({"path_corr": "not-a-number"})["path_corr"] is None

    def test_numeric_string_n_is_coerced(self):
        # int() 直接转换: 数字字符串 "400" 可被强转 (与 _f 保护的浮点字段不同)
        m = fm.map_summary({"n": "400", "n_eff": "50"})
        assert m["n"] == 400
        assert m["n_eff"] == 50

    def test_non_numeric_n_falls_back_to_default(self):
        # 2026-09-17 修复审计 bug #5: 整数字段补 _i 防护 (与浮点字段 _f 一致),
        # n="abc" 回退默认 0 而非抛 ValueError; n_eff 非法时回退到 n
        m = fm.map_summary({"n": "abc"})
        assert m["n"] == 0
        assert m["n_eff"] == 0
        assert fm.map_summary({"n": 400, "n_eff": "abc"})["n_eff"] == 400

    def test_nan_dir_acc_propagates_and_gate_fails_closed(self):
        # NaN dir_acc 原样通过 _f (float(nan) 成功) → gate 判 False (fail-closed):
        # 脏指标绝不能变成放行信号
        m = fm.map_summary({"dir_acc": float("nan")})
        assert math.isnan(m["dir_acc"])
        assert fm.gate({"n": 400, "n_eff": 400, "dir_acc": float("nan")}) is False


# ══════════════════ gate ══════════════════

class TestGateBoundaries:
    """硬门 n>=350 / n_eff>=50 / dir_acc>=0.52 是品种晋升的唯一通道, 边界语义必须是闭区间."""

    @pytest.mark.parametrize("field,value", [
        ("n", 350), ("n_eff", 50), ("dir_acc", 0.52),
    ])
    def test_exact_thresholds_pass(self, field, value):
        # 恰好压线的指标必须通过 (>= 语义), 否则预注册口径无法复现
        s = {"n": 400, "n_eff": 400, "dir_acc": 0.56}
        s[field] = value
        assert fm.gate(s) is True

    @pytest.mark.parametrize("field,value", [
        ("n", 349), ("n_eff", 49), ("dir_acc", 0.5199),
    ])
    def test_one_below_threshold_fails(self, field, value):
        s = {"n": 400, "n_eff": 400, "dir_acc": 0.56}
        s[field] = value
        assert fm.gate(s) is False

    @pytest.mark.parametrize("missing", ["n", "n_eff", "dir_acc"])
    def test_missing_any_metric_fails_closed(self, missing):
        # 任一指标缺失 (键不存在) → 不晋升: 缺证据 = 不过门
        s = {"n": 400, "n_eff": 400, "dir_acc": 0.56}
        del s[missing]
        assert fm.gate(s) is False

    def test_adaptive_floor_at_0_50(self):
        # baseline 弱 (0.45) 时门不能跟着塌: 有效下限钳在 0.50
        s = {"n": 400, "n_eff": 400, "dir_acc": 0.505}
        assert fm.gate(s, baseline_dir_acc=0.45) is True
        assert fm.gate({**s, "dir_acc": 0.49}, baseline_dir_acc=0.45) is False

    def test_adaptive_cap_at_min_dir_acc(self):
        # baseline 强 (0.55) 时 0.52 底线仍在: 门不能被拉高超过预注册口径
        s = {"n": 400, "n_eff": 400, "dir_acc": 0.52}
        assert fm.gate(s, baseline_dir_acc=0.55) is True

    def test_gate_nan_n_fail_closed(self):
        # 2026-09-17 修复审计 bug #1: n=NaN 不再 fail-open 绕过硬门, 统一 fail-closed 拒绝
        assert fm.gate({"n": float("nan"), "n_eff": 400, "dir_acc": 0.56}) is False
        assert fm.gate({"n": 400, "n_eff": float("nan"), "dir_acc": 0.56}) is False

    def test_gate_dir_acc_inf_rejected(self):
        # 2026-09-17 修复审计 bug #2: dir_acc=inf 不再通过硬门, 非有限值一律拒绝
        assert fm.gate({"n": 400, "n_eff": 400, "dir_acc": float("inf")}) is False
        assert fm.gate({"n": 400, "n_eff": 400, "dir_acc": float("-inf")}) is False


# ══════════════════ effective_sample_size ══════════════════

class TestEffectiveSampleSizeBoundaries:
    """Bartlett ESS 修正重叠窗口的名义样本膨胀; 边界错误会直接扭曲 n_eff 硬门."""

    @pytest.mark.parametrize("step,horizon", [(24, 24), (48, 24)])
    def test_non_overlapping_returns_nominal(self, step, horizon):
        # step>=horizon → 窗口无重叠 → 无方差膨胀, n_eff == 名义 n
        assert fm.effective_sample_size(400, horizon=horizon, step=step) == 400

    def test_step_zero_raises_value_error(self):
        # 2026-09-17 修复审计 bug #7: step<=0 为非法参数, 显式抛 ValueError
        with pytest.raises(ValueError):
            fm.effective_sample_size(400, horizon=24, step=0)

    def test_autocorr_zero_returns_nominal(self):
        # 无残余自相关 → Bartlett 核积分为 0 → VIF=1
        assert fm.effective_sample_size(400, horizon=24, step=2,
                                        residual_autocorr=0.0) == 400

    def test_default_autocorr_is_0_9(self):
        # 缺省 residual_autocorr=None → 0.9: 结果必须与显式传 0.9 完全一致
        a = fm.effective_sample_size(400, horizon=24, step=2)
        b = fm.effective_sample_size(400, horizon=24, step=2, residual_autocorr=0.9)
        assert a == b

    def test_exact_formula_step1_horizon2(self):
        # 手算锚点: max_overlap=1, w=0.5, kernel=0.5*rho → VIF=1+rho → 100/1.5 → 66
        assert fm.effective_sample_size(100, horizon=2, step=1,
                                        residual_autocorr=0.5) == 66

    def test_monotonic_decreasing_in_autocorr(self):
        # 自相关越强, 重叠膨胀越严重, n_eff 单调不增 — 硬门的统计保守性来源
        ess = [fm.effective_sample_size(400, horizon=24, step=2, residual_autocorr=r)
               for r in (0.0, 0.5, 0.9, 1.0)]
        assert ess == sorted(ess, reverse=True)

    def test_negative_autocorr_inflates_beyond_nominal(self):
        # [PIN] 负自相关 → VIF<1 → n_eff 超过名义 n (无上限帽), 结果 floor 到 >=1。
        n_eff = fm.effective_sample_size(400, horizon=24, step=2,
                                         residual_autocorr=-0.9)
        assert n_eff > 400
        assert n_eff >= 1

    def test_nominal_zero_floors_at_1(self):
        # [PIN] nominal_n=0 → 0/VIF → max(1, 0) = 1: 零样本不会产出 n_eff=0
        n_eff = fm.effective_sample_size(0, horizon=24, step=2)
        assert n_eff == 1


# ══════════════════ build_summary 错误路径 ══════════════════

def _aligned_cand():
    return {"symbol": "m", "cov_override": "rsi_state",
            "max_points": 400, "stage": "aligned"}


def _mk_points(n_pairs, v_rate=0.6, b_rate=0.4):
    """确定性构造 (cutoff, dir_ok) 点列: variant v_rate / baseline b_rate."""
    variant, baseline = [], []
    for i in range(n_pairs):
        ts = f"2024-06-15 {i // 60:02d}:{i % 60:02d}:00"
        variant.append((ts, i % 5 < 3))
        baseline.append({"cutoff": ts, "dir_ok": i % 5 < 2})
    return variant, baseline


class TestBuildSummaryErrorPaths:
    """build_summary 是裁定输出的最终组装点; DM 异常与 None 输入决定证据链完整性."""

    @pytest.mark.parametrize("n_pairs,expect_p", [(99, None), (100, "float")])
    def test_dm_pair_boundary_99_vs_100(self, n_pairs, expect_p):
        # 配对样本恰好 100 才跑 DM 检验: 99 → p_value=None, 100 → 浮点 p 值
        s = {"n": 400, "n_eff": 400, "dir_acc": 0.56, "endpoint_mape": 0.4,
             "endpoint_bias_pct": 0.1, "path_corr": 0.7, "weighted_dir_acc": 0.57,
             "mae": 1.0, "mape": 0.4, "decay": 1.1,
             "point_dir_ok_list": _mk_points(n_pairs)[0]}
        base = _mk_points(n_pairs)[1]
        out = fm.build_summary(s, _aligned_cand(), baseline_points=base)
        if expect_p is None:
            assert out["p_value"] is None
        else:
            assert isinstance(out["p_value"], float)
            assert 0.0 <= out["p_value"] < 1.0

    def test_dm_exception_swallowed_status_still_ok(self, monkeypatch):
        # 统计模块崩溃 (scipy/数据畸形) 不得拖垮裁定输出: p_value 回退 None, status 保持 ok
        def _boom(*a, **k):
            raise RuntimeError("statistical module down")
        monkeypatch.setattr(fm, "pair_dir_ok_series", _boom)
        s = {"n": 400, "n_eff": 400, "dir_acc": 0.56, "endpoint_mape": 0.4,
             "endpoint_bias_pct": 0.1, "path_corr": 0.7, "weighted_dir_acc": 0.57,
             "mae": 1.0, "mape": 0.4, "decay": 1.1,
             "point_dir_ok_list": _mk_points(120)[0]}
        out = fm.build_summary(s, _aligned_cand(), baseline_points=_mk_points(120)[1])
        assert out["status"] == "ok"
        assert out["p_value"] is None

    def test_point_dir_ok_list_none_tolerated_no_pvalue(self):
        # 2026-09-17 修复审计 bug #4: point_dir_ok_list 键存在但值为 None 时
        # 回退空列表 (不抛 TypeError), DM 不跑 → p_value=None, status 保持 ok
        s = {"n": 400, "n_eff": 400, "dir_acc": 0.56, "endpoint_mape": 0.4,
             "endpoint_bias_pct": 0.1, "path_corr": 0.7, "weighted_dir_acc": 0.57,
             "mae": 1.0, "mape": 0.4, "decay": 1.1,
             "point_dir_ok_list": None}
        out = fm.build_summary(s, _aligned_cand(), baseline_points=_mk_points(120)[1])
        assert out["status"] == "ok"
        assert out["p_value"] is None

    def test_empty_baseline_list_no_pvalue(self):
        # baseline_points=[] (非 None 的空列表): 走 None 检查但不满足 >=100 → p_value=None
        s = {"n": 400, "n_eff": 400, "dir_acc": 0.56, "endpoint_mape": 0.4,
             "endpoint_bias_pct": 0.1, "path_corr": 0.7, "weighted_dir_acc": 0.57,
             "meta_note": "unused", "mae": 1.0, "mape": 0.4, "decay": 1.1,
             "point_dir_ok_list": _mk_points(120)[0]}
        out = fm.build_summary(s, _aligned_cand(), baseline_points=[])
        assert out["p_value"] is None
        assert out["status"] == "ok"

    def test_point_list_consumed_even_on_short_series(self):
        # 即使样本不足 DM 未跑, 输入 s 中的 point_dir_ok_list 也必须被 pop 原地消费
        # (pop 改的是调用方传入的 dict — 防原始点残留在调用方数据中二次泄漏)
        s = {"n": 400, "n_eff": 400, "dir_acc": 0.56, "endpoint_mape": 0.4,
             "endpoint_bias_pct": 0.1, "path_corr": 0.7, "weighted_dir_acc": 0.57,
             "mae": 1.0, "mape": 0.4, "decay": 1.1,
             "point_dir_ok_list": _mk_points(10)[0]}
        out = fm.build_summary(s, _aligned_cand())
        assert "point_dir_ok_list" not in s
        assert "point_dir_ok_list" not in out
        assert "point_dir_ok_list" not in out["metrics"]


# ════ pair_dir_ok_series / diebold_mariano_p (evaluator 从 cascade 导入的统计检验边界) ════

class TestPairDirOkSeriesBoundaries:
    """配对逻辑决定 DM 检验的样本完整性: 重复/非法时间戳直接改变统计样本量."""

    def test_empty_inputs_return_empty_series(self):
        # 双侧空序列 → 空配对, 上游 DM 以 len<100 防护
        assert fm.pair_dir_ok_series([], []) == ([], [])

    def test_duplicate_cutoff_last_write_wins(self):
        # 重复时间戳: dict 覆盖语义 → 后写胜出, 重复点不得让配对样本虚增
        variant = [("2024-06-15 09:00:00", 1), ("2024-06-15 09:00:00", 0)]
        baseline = [{"cutoff": "2024-06-15 09:00:00", "dir_ok": 1}]
        v, b = fm.pair_dir_ok_series(variant, baseline)
        assert v == [0]
        assert b == [1]

    @pytest.mark.parametrize("bad_cutoff", ["not-a-date", "", "20240615"])
    def test_invalid_cutoff_dropped(self, bad_cutoff):
        # 非法 cutoff (含 <9 位数字串 "20240615" — spec 9.4 防误判) 必须被丢弃而非崩溃
        variant = [(bad_cutoff, 1), ("2024-06-15 09:00:00", 1)]
        baseline = [{"cutoff": "2024-06-15 09:00:00", "dir_ok": 0}]
        v, b = fm.pair_dir_ok_series(variant, baseline)
        assert v == [1]
        assert b == [0]

    def test_mixed_tuple_dict_formats_join(self):
        # variant 走 tuple, baseline 走 dict — build_summary 的真实调用形态
        variant = [("2024-06-15 09:00:00", 1), ("2024-06-15 10:00:00", 0)]
        baseline = [{"cutoff": "2024-06-15 09:00:00", "dir_ok": 0},
                    {"cutoff": "2024-06-15 10:00:00", "dir_ok": 1}]
        v, b = fm.pair_dir_ok_series(variant, baseline)
        assert v == [1, 0]
        assert b == [0, 1]

    def test_datetime_vs_string_normalize_equally(self):
        # naive datetime 与 ISO 字符串应归一到同一时戳 (Asia/Shanghai) 完成配对
        from datetime import datetime
        variant = [(datetime(2024, 6, 15, 9, 0, 0), 1)]
        baseline = [{"cutoff": "2024-06-15 09:00:00", "dir_ok": 0}]
        v, b = fm.pair_dir_ok_series(variant, baseline)
        assert v == [1] and b == [0]

    def test_dict_point_missing_fields_dropped(self):
        # dict 点缺 cutoff/dir_ok → 该点丢弃, 不崩溃 (部分损坏数据不拖垮整体配对)
        variant = [{"cutoff": None, "dir_ok": 1}, ("2024-06-15 09:00:00", 1)]
        baseline = [{"cutoff": "2024-06-15 09:00:00", "dir_ok": 0}]
        v, b = fm.pair_dir_ok_series(variant, baseline)
        assert v == [1] and b == [0]


class TestDieboldMarianoErrorPaths:
    """DM 检验是变体优于基线的唯一统计证据; 退化输入必须保守回退 1.0 (不拒绝 H0)."""

    @staticmethod
    def _series(n, v_rate, b_rate):
        v = [1 if i % 5 < int(v_rate * 5) else 0 for i in range(n)]
        b = [1 if i % 5 < int(b_rate * 5) else 0 for i in range(n)]
        return v, b

    def test_identical_series_conservative_1_0(self):
        # 零差分序列 (variant==baseline): d_bar=0 → 保守返回 1.0, 绝不产伪显著
        v, b = self._series(120, 0.6, 0.6)
        assert fm.diebold_mariano_p(v, b) == 1.0

    def test_variant_worse_returns_1_0(self):
        # variant 劣于基线 (d_bar<0): 单侧 H1 是"更好", 劣势直接回退 1.0
        v, b = self._series(120, 0.4, 0.6)
        assert fm.diebold_mariano_p(v, b) == 1.0

    @pytest.mark.parametrize("n", [50, 99])
    def test_sample_below_100_returns_1_0(self, n):
        # 样本 <100 统计功效不足: 不产证据 (build_summary 侧还有 >=100 双重防护)
        v, b = self._series(n, 0.6, 0.4)
        assert fm.diebold_mariano_p(v, b) == 1.0

    def test_length_mismatch_returns_1_0(self):
        # 配对长度不一致说明配对逻辑被破坏 → 保守回退而非 NaN 传播
        v, _ = self._series(120, 0.6, 0.4)
        b = self._series(119, 0.4, 0.4)[0]
        assert fm.diebold_mariano_p(v, b) == 1.0

    def test_strong_advantage_yields_small_p(self):
        # 100 配对、variant 80% vs baseline 40% → 必须显著 (p<0.05):
        # 防止检验退化成"永远 1.0"的假安全阀 (有功效才能拒绝 H0)
        v, b = self._series(100, 0.8, 0.4)
        p = fm.diebold_mariano_p(v, b)
        assert 0.0 <= p < 0.05

    def test_zero_variance_differential_returns_1_0(self):
        # [PIN] 零方差守卫: d 恒定 (全 1 vs 全 0) → HAC 方差 V=0 → V<=1e-12
        # 直接回退 1.0, 不经过 HLN 调整/clip 路径 — 零方差差分绝不产伪 p 值
        v, b = self._series(100, 1.0, 0.0)
        assert fm.diebold_mariano_p(v, b) == 1.0
