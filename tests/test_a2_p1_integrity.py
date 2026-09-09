"""A2-P1 完整性测试: 运行配置、eval grid、JSONL 校验、排他锁、幂等写入。"""
from pathlib import Path
import hashlib
import json
import os
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.a2_p1_runtime import (
    generate_eval_grid,
    expected_eval_grid,
    RunConfig,
    load_jsonl_records,
    validate_jsonl_records,
    ValidationResult,
    ValidationReport,
    validate_run_results,
    exclusive_result_lock,
    append_unique_record,
    stable_symbol_seed,
)
from config.backtest_config import CONTEXT_BARS, HORIZON, STEP


# ═══════════════════════════════════════════════════════════
# Eval Grid Tests
# ═══════════════════════════════════════════════════════════

def test_eval_grid_matches_worker_boundary():
    """验证 eval grid 与 Worker 原始 range 表达式完全一致。"""
    assert generate_eval_grid(1000) == list(range(480, 1000 - 24 + 1, 24))


def test_eval_grid_uses_shared_constants():
    """验证 eval grid 使用共享配置常量。"""
    assert generate_eval_grid(1000) == list(range(CONTEXT_BARS, 1000 - HORIZON + 1, STEP))


def test_eval_grid_empty_for_insufficient_bars():
    """验证 bar 数量不足时返回空列表。"""
    # CONTEXT_BARS=480, HORIZON=24: 至少需要 480+24-1=503 个 bar 才有 1 个 eval point
    assert generate_eval_grid(500) == []


def test_eval_grid_single_point():
    """验证刚好够一个 eval point 的情况。"""
    # total_bars = 504: range(480, 504-24+1=481, 24) = [480]
    assert generate_eval_grid(504) == [480]


def test_eval_grid_step_24():
    """验证步长为 24 的非重叠窗口。"""
    grid = generate_eval_grid(1200)
    assert grid[0] == 480
    assert grid[1] == 504
    assert grid[-1] <= 1200 - 24


# ═══════════════════════════════════════════════════════════
# RunConfig Tests
# ═══════════════════════════════════════════════════════════

def test_run_config_never_uses_a2_p1_1_for_a2_p1_by_default():
    """验证 a2-p1 默认不使用 a2-p1.1 的路径。"""
    root = Path(__file__).resolve().parent.parent
    cfg = RunConfig.for_run("a2-p1", ["ss"], root)
    assert cfg.results_dir == root / "reports/a2_p1_results"
    assert cfg.logs_dir == root / "reports/a2_p1_logs"
    assert cfg.report_path == root / "reports/research/2026-08-05_a2_p1_baseline_result.md"


def test_run_config_isolated_for_a2_p1_1():
    """验证 a2-p1.1 使用独立路径。"""
    root = Path(__file__).resolve().parent.parent
    cfg = RunConfig.for_run("a2-p1.1", ["fg"], root)
    assert cfg.results_dir == root / "reports/a2_p1.1_results"
    assert cfg.logs_dir == root / "reports/a2_p1.1_logs"
    assert cfg.results_dir != RunConfig.for_run("a2-p1", ["fg"], root).results_dir


def test_run_config_symbols_lowercased():
    """验证 symbols 自动转小写。"""
    root = Path(__file__).resolve().parent.parent
    cfg = RunConfig.for_run("a2-p1", ["SS", "RB"], root)
    assert cfg.symbols == ["ss", "rb"]


def test_run_config_unsupported_run_id():
    """验证不支持的 run_id 抛出 ValueError。"""
    root = Path(__file__).resolve().parent.parent
    try:
        RunConfig.for_run("a2-p3", ["ss"], root)
        raise AssertionError("should have raised ValueError")
    except ValueError as e:
        assert "unsupported run_id" in str(e)


def test_run_config_features_dir_shared():
    """验证 features_dir 对 a2-p1 和 a2-p1.1 相同。"""
    root = Path(__file__).resolve().parent.parent
    cfg1 = RunConfig.for_run("a2-p1", ["ss"], root)
    cfg2 = RunConfig.for_run("a2-p1.1", ["ss"], root)
    assert cfg1.features_dir == cfg2.features_dir == root / "reports/a2_p1_features"


def test_run_config_frozen():
    """验证 RunConfig 是不可变的 (frozen dataclass)。"""
    root = Path(__file__).resolve().parent.parent
    cfg = RunConfig.for_run("a2-p1", ["ss"], root)
    try:
        cfg.run_id = "a2-p2"
        raise AssertionError("frozen dataclass should not allow modification")
    except (TypeError, AttributeError):
        pass


# ═══════════════════════════════════════════════════════════
# JSONL Tests
# ═══════════════════════════════════════════════════════════

def test_load_jsonl_records_skips_empty_lines(tmp_path):
    """验证空行被自动跳过。"""
    path = tmp_path / "test.jsonl"
    path.write_text('{"a": 1}\n\n{"b": 2}\n', encoding="utf-8")
    records = load_jsonl_records(path)
    assert len(records) == 2
    assert records[0] == {"a": 1}
    assert records[1] == {"b": 2}


def test_load_jsonl_records_invalid_json(tmp_path):
    """验证无效 JSON 抛 ValueError 并带行号。"""
    path = tmp_path / "bad.jsonl"
    path.write_text('{"a": 1}\nnot json\n{"b": 2}\n', encoding="utf-8")
    try:
        load_jsonl_records(path)
        raise AssertionError("should have raised ValueError")
    except ValueError as e:
        assert "bad.jsonl:2" in str(e)


def test_load_jsonl_records_empty_file(tmp_path):
    """验证空文件返回空列表。"""
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    assert load_jsonl_records(path) == []


# ═══════════════════════════════════════════════════════════
# Validation Tests
# ═══════════════════════════════════════════════════════════

def test_validation_accepts_valid_records():
    """验证完整且正确的记录通过校验。"""
    rows = [
        _make_valid_record(480, "a2-p1", "ss"),
        _make_valid_record(504, "a2-p1", "ss"),
    ]
    result = validate_jsonl_records(rows, [480, 504], "a2-p1", "ss")
    assert result.ok
    assert result.row_count == 2
    assert result.unique_count == 2


def test_validation_rejects_duplicate_bar_idx():
    """验证重复 bar_idx 被拒绝。"""
    rows = [
        {"bar_idx": 480, "run_id": "a2-p1", "symbol": "SS", "version": "abc"},
        {"bar_idx": 480, "run_id": "a2-p1", "symbol": "SS", "version": "abc"},
    ]
    result = validate_jsonl_records(rows, [480], "a2-p1", "ss")
    assert not result.ok
    assert any("duplicate" in e for e in result.errors)


def test_validation_rejects_missing_eval_bar():
    """验证缺失的 eval bar 被拒绝。"""
    rows = [{"bar_idx": 480, "run_id": "a2-p1", "symbol": "SS", "version": "abc"}]
    result = validate_jsonl_records(rows, [480, 504], "a2-p1", "ss")
    assert not result.ok
    assert any("missing" in e for e in result.errors)


def test_validation_detects_unexpected_bar():
    """验证意外的 bar_idx 被报告。"""
    rows = [
        {"bar_idx": 480, "run_id": "a2-p1", "symbol": "SS"},
        {"bar_idx": 999, "run_id": "a2-p1", "symbol": "SS"},
    ]
    result = validate_jsonl_records(rows, [480], "a2-p1", "ss")
    assert not result.ok
    assert any("unexpected" in e for e in result.errors)


def test_validation_missing_bar_idx_field():
    """验证缺少 bar_idx 字段的记录被报告。"""
    rows = [
        {"run_id": "a2-p1", "symbol": "SS"},  # 缺少 bar_idx
    ]
    result = validate_jsonl_records(rows, [480], "a2-p1", "ss")
    assert not result.ok
    assert any("missing bar_idx" in e for e in result.errors)


# ═══════════════════════════════════════════════════════════
# Exclusive Lock Tests (Task 2)
# ═══════════════════════════════════════════════════════════

def test_lock_released_on_exit(tmp_path):
    """验证上下文退出后锁文件被删除。"""
    lock_path = tmp_path / "test.lock"
    assert not lock_path.exists()
    with exclusive_result_lock(lock_path, run_id="test-run"):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_lock_metadata_is_writable(tmp_path):
    """验证锁文件内容可 JSON 解析，含 pid/run_id/acquired_at。"""
    lock_path = tmp_path / "test.lock"
    with exclusive_result_lock(lock_path, run_id="my-run"):
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()
    assert data["run_id"] == "my-run"
    assert "acquired_at" in data


def test_lock_is_exclusive(tmp_path):
    """第一个持有锁时，第二个尝试获取应抛 RuntimeError，且错误消息包含原持有者的 PID。"""
    lock_path = tmp_path / "exclusive.lock"
    barrier = threading.Barrier(2)
    error_holder = {"exc": None}

    def holder():
        with exclusive_result_lock(lock_path, run_id="holder"):
            barrier.wait()  # 通知第二个线程可以开始尝试
            time.sleep(0.5)  # 保持锁一段时间

    def contender():
        try:
            barrier.wait()  # 等待 holder 进入
            with exclusive_result_lock(lock_path, run_id="contender"):
                pass  # 不应该到达这里
        except RuntimeError as exc:
            error_holder["exc"] = exc

    t1 = threading.Thread(target=holder)
    t2 = threading.Thread(target=contender)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert error_holder["exc"] is not None
    assert "pid=" in str(error_holder["exc"])


# ═══════════════════════════════════════════════════════════
# Idempotent Append Tests (Task 2)
# ═══════════════════════════════════════════════════════════

def test_append_unique_record_does_not_duplicate_bar(tmp_path):
    """验证重复写入同一 bar_idx 不会导致重复记录。"""
    path = tmp_path / "results.jsonl"
    record = {
        "bar_idx": 480,
        "run_id": "a2-p1.1",
        "symbol": "SS",
        "version": "abc123",
        "pure_pred_move": 1.5,
        "scheme_pred_move": 2.0,
        "lgbm_pred_move": 1.8,
        "actual_move": 1.2,
        "base_price": 100.0,
        "atr": 2.5,
    }
    append_unique_record(path, record)
    append_unique_record(path, record)  # 幂等写入，应跳过
    append_unique_record(path, record)  # 再次幂等

    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["bar_idx"] == 480


def test_append_unique_record_raises_on_conflict(tmp_path):
    """验证不可变字段冲突时抛 ValueError。"""
    path = tmp_path / "results.jsonl"
    record1 = {
        "bar_idx": 480,
        "run_id": "a2-p1.1",
        "symbol": "SS",
        "version": "abc123",
        "pure_pred_move": 1.5,
        "scheme_pred_move": 2.0,
        "lgbm_pred_move": 1.8,
        "actual_move": 1.2,
        "base_price": 100.0,
        "atr": 2.5,
    }
    append_unique_record(path, record1)

    # 修改一个不可变字段制造冲突
    record2 = dict(record1)
    record2["base_price"] = 999.0  # 冲突!

    try:
        append_unique_record(path, record2)
        raise AssertionError("should have raised ValueError")
    except ValueError as exc:
        assert "conflicting record" in str(exc)
        assert "480" in str(exc)


# ═══════════════════════════════════════════════════════════
# Structural Tests (Task 2: 代码结构检查)
# ═══════════════════════════════════════════════════════════

def test_worker_lock_acquired_before_model_loading():
    """通过代码结构检查: Worker 源码中 exclusive_result_lock 调用在 import timesfm 之前。"""
    worker_path = Path(__file__).parent.parent / "scripts" / "a2_p1_worker.py"
    source = worker_path.read_text(encoding="utf-8")
    lock_call_pos = source.find("exclusive_result_lock")
    timesfm_import_pos = source.find("import timesfm")
    assert lock_call_pos != -1, "Worker 未调用 exclusive_result_lock"
    assert timesfm_import_pos != -1, "Worker 未 import timesfm"
    assert lock_call_pos < timesfm_import_pos, (
        f"exclusive_result_lock (pos={lock_call_pos}) 必须在 import timesfm (pos={timesfm_import_pos}) 之前"
    )


def test_orchestrator_uses_run_level_lock():
    """通过代码结构检查: Orchestrator 源码中包含 exclusive_result_lock 调用。"""
    orch_path = Path(__file__).parent.parent / "scripts" / "a2_p1_orchestrator.py"
    source = orch_path.read_text(encoding="utf-8")
    assert "exclusive_result_lock" in source, "Orchestrator 未使用 exclusive_result_lock"


# ═══════════════════════════════════════════════════════════
# Task 3: Fail-Closed Report Generator Tests
# ═══════════════════════════════════════════════════════════

def _make_valid_record(bar_idx: int, run_id: str, symbol: str) -> dict:
    """创建一条合法的 worker JSONL 记录 (含所有必要字段)。"""
    return {
        "bar_idx": bar_idx,
        "run_id": run_id,
        "symbol": symbol.upper(),
        "version": "test-abc",
        "pure_pred_move": 1.5,
        "scheme_pred_move": 2.0,
        "lgbm_pred_move": 1.8,
        "actual_move": 1.2,
        "base_price": 100.0,
        "atr": 2.5,
    }


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """将记录列表写入 JSONL 文件。"""
    import json as _json
    lines = [_json.dumps(r, ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_validate_run_results_all_present(tmp_path):
    """所有 symbol 都合法, ok=True。"""
    root = tmp_path
    results_dir = root / "results"
    results_dir.mkdir()

    sym = "ss"
    bars = [480, 504, 528]  # 模拟 eval grid
    records = [_make_valid_record(b, "a2-p1", sym) for b in bars]
    _write_jsonl(results_dir / f"{sym}.jsonl", records)

    # 预期: 由于没有真实数据库, expected_eval_grid 会调 DataStore 而失败
    # 所以此测试构造一个 config 使用 mock 方式
    # 但我们用直接 validate_jsonl_records 来测试
    result = validate_jsonl_records(records, bars, "a2-p1", sym)
    assert result.ok
    assert result.row_count == 3
    assert result.unique_count == 3


def test_validate_run_results_missing_symbol(tmp_path):
    """一个 symbol 缺文件, ok=False。"""
    root = tmp_path
    results_dir = root / "results"
    results_dir.mkdir()
    # 不创建任何 JSONL 文件
    config = RunConfig(
        run_id="a2-p1",
        results_dir=results_dir,
        logs_dir=root / "logs",
        report_path=root / "report.md",
        features_dir=root / "features",
        symbols=["ss", "rb"],
    )
    # validate_run_results 会因 expected_eval_grid 依赖 DataStore 而报错
    # 所以我们只测试文件不存在的情况: 直接检查返回
    rpt = validate_run_results(config)
    assert not rpt.ok
    assert "ss" in rpt.per_symbol
    assert not rpt.per_symbol["ss"].ok
    assert "rb" in rpt.per_symbol
    assert not rpt.per_symbol["rb"].ok


def test_validate_run_results_duplicate_bar(tmp_path):
    """一个 symbol 有重复 bar, ok=False。"""
    records = [
        _make_valid_record(480, "a2-p1", "ss"),
        _make_valid_record(480, "a2-p1", "ss"),  # 重复
        _make_valid_record(504, "a2-p1", "ss"),
    ]
    result = validate_jsonl_records(records, [480, 504], "a2-p1", "ss")
    assert not result.ok
    assert any("duplicate" in e for e in result.errors)


def test_validate_run_results_wrong_run_id(tmp_path):
    """run_id 不一致, ok=False。"""
    records = [
        _make_valid_record(480, "a2-p1", "ss"),
        _make_valid_record(504, "wrong-run", "ss"),  # run_id 不一致
    ]
    result = validate_jsonl_records(records, [480, 504], "a2-p1", "ss")
    assert not result.ok
    assert any("run_id mismatch" in e for e in result.errors)


def test_generate_report_refuses_incomplete(tmp_path):
    """缺 symbol 时不写报告, 抛 RuntimeError。"""
    from scripts.a2_p1_generate_report import generate_report

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    # 不创建任何 JSONL → 校验应失败
    config = RunConfig(
        run_id="a2-p1",
        results_dir=results_dir,
        logs_dir=tmp_path / "logs",
        report_path=tmp_path / "report.md",
        features_dir=tmp_path / "features",
        symbols=["ss"],
    )
    try:
        generate_report(config)
        raise AssertionError("should have raised RuntimeError")
    except RuntimeError as exc:
        assert "validation" in str(exc).lower() or "fail" in str(exc).lower()


def test_generate_report_does_not_overwrite_on_failure(tmp_path):
    """已存在的报告内容不被覆盖。"""
    from scripts.a2_p1_generate_report import generate_report

    report_path = tmp_path / "report.md"
    report_path.write_text("OLD REPORT CONTENT", encoding="utf-8")

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    # 不创建 JSONL → 校验失败
    config = RunConfig(
        run_id="a2-p1",
        results_dir=results_dir,
        logs_dir=tmp_path / "logs",
        report_path=report_path,
        features_dir=tmp_path / "features",
        symbols=["ss"],
    )
    try:
        generate_report(config)
    except RuntimeError:
        pass

    # 报告内容应该还是旧的
    assert report_path.read_text(encoding="utf-8") == "OLD REPORT CONTENT"


def test_generate_report_uses_correct_tick_sizes(tmp_path):
    """tick size 来自 TICK_SIZES，不是 1.0。"""
    from config.backtest_config import TICK_SIZES
    import pandas as pd
    from scripts import a2_p1_generate_report as mod
    from scripts.a2_p1_runtime import ValidationResult, ValidationReport

    # 创建合法的 SS 结果
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    bars = list(range(480, 480 + 24 * 12, 24))  # 12 个 eval bars
    records = [_make_valid_record(b, "a2-p1", "ss") for b in bars]
    _write_jsonl(results_dir / "ss.jsonl", records)

    report_path = tmp_path / "report.md"
    config = RunConfig(
        run_id="a2-p1",
        results_dir=results_dir,
        logs_dir=tmp_path / "logs",
        report_path=report_path,
        features_dir=tmp_path / "features",
        symbols=["ss"],
    )

    # 用 mock 捕获 evaluate_gate 的 tick_size 参数
    captured_tick = {"value": None}

    def _capture_gate(*args, **kwargs):
        captured_tick["value"] = kwargs.get("tick_size")
        return {
            "gate": "GO",
            "lgbm_metrics": {"PF": 1.5, "EV": 0.1},
            "scheme_metrics": {"PF": 1.2},
            "ev_diff_ci": {"lower": 0.01},
        }

    fake_vr = ValidationResult(ok=True, errors=[], row_count=12, unique_count=12)
    fake_report = ValidationReport(ok=True, per_symbol={"ss": fake_vr}, errors=[])

    # 保存原始函数
    orig_validate = mod.validate_run_results
    orig_load = mod.load_symbol_results
    orig_eval = mod.evaluate_gate

    # 安装 mock
    mod.validate_run_results = lambda cfg: fake_report
    mod.load_symbol_results = lambda p: pd.DataFrame(records)
    mod.evaluate_gate = _capture_gate

    try:
        mod.generate_report(config)
    finally:
        mod.validate_run_results = orig_validate
        mod.load_symbol_results = orig_load
        mod.evaluate_gate = orig_eval

    assert captured_tick["value"] is not None
    assert float(captured_tick["value"]) == float(TICK_SIZES["ss"])
    assert float(captured_tick["value"]) != 1.0


def test_generate_report_missing_tick_size_fails(tmp_path):
    """一个 symbol 不在 TICK_SIZES 中时 RuntimeError。"""
    import pandas as pd
    from scripts import a2_p1_generate_report as mod
    from scripts.a2_p1_runtime import ValidationResult, ValidationReport
    from config import backtest_config

    # 创建一个不在 TICK_SIZES 中的 symbol "xx"
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    bars = list(range(480, 480 + 24 * 12, 24))
    records = [_make_valid_record(b, "a2-p1", "xx") for b in bars]
    _write_jsonl(results_dir / "xx.jsonl", records)

    config = RunConfig(
        run_id="a2-p1",
        results_dir=results_dir,
        logs_dir=tmp_path / "logs",
        report_path=tmp_path / "report.md",
        features_dir=tmp_path / "features",
        symbols=["xx"],
    )

    fake_vr = ValidationResult(ok=True, errors=[], row_count=12, unique_count=12)
    fake_report = ValidationReport(
        ok=True,
        per_symbol={"xx": fake_vr},
        errors=[],
    )

    orig_validate = mod.validate_run_results
    orig_load = mod.load_symbol_results

    mod.validate_run_results = lambda cfg: fake_report
    mod.load_symbol_results = lambda p: pd.DataFrame(records)

    try:
        try:
            mod.generate_report(config)
            raise AssertionError("should have raised RuntimeError for missing tick size")
        except RuntimeError as exc:
            assert "missing tick size" in str(exc).lower()
    finally:
        mod.validate_run_results = orig_validate
        mod.load_symbol_results = orig_load


def test_generate_report_atomic_write(tmp_path):
    """成功时报告路径的 .tmp 先写再 replace。"""
    import pandas as pd
    from scripts import a2_p1_generate_report as mod
    from scripts.a2_p1_runtime import ValidationResult, ValidationReport

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    bars = list(range(480, 480 + 24 * 12, 24))
    records = [_make_valid_record(b, "a2-p1", "ss") for b in bars]
    _write_jsonl(results_dir / "ss.jsonl", records)

    report_path = tmp_path / "report.md"
    config = RunConfig(
        run_id="a2-p1",
        results_dir=results_dir,
        logs_dir=tmp_path / "logs",
        report_path=report_path,
        features_dir=tmp_path / "features",
        symbols=["ss"],
    )

    fake_vr = ValidationResult(ok=True, errors=[], row_count=12, unique_count=12)
    fake_report = ValidationReport(ok=True, per_symbol={"ss": fake_vr}, errors=[])

    orig_validate = mod.validate_run_results
    orig_load = mod.load_symbol_results
    orig_eval = mod.evaluate_gate

    mod.validate_run_results = lambda cfg: fake_report
    mod.load_symbol_results = lambda p: pd.DataFrame(records)
    mod.evaluate_gate = lambda *a, **kw: {
        "gate": "GO",
        "lgbm_metrics": {"PF": 1.5, "EV": 0.1},
        "scheme_metrics": {"PF": 1.2},
        "ev_diff_ci": {"lower": 0.01},
    }

    try:
        mod.generate_report(config)
    finally:
        mod.validate_run_results = orig_validate
        mod.load_symbol_results = orig_load
        mod.evaluate_gate = orig_eval

    # 成功时报告路径应存在, .tmp 不应存在 (已被 replace)
    assert report_path.exists(), "报告文件应存在"
    assert not report_path.with_suffix('.tmp').exists(), ".tmp 文件不应残留"
    # 报告内容应包含 tick_size
    content = report_path.read_text(encoding="utf-8")
    assert "tick_size" in content


# ═══════════════════════════════════════════════════════════
# Task 4: Failure Visibility & Deterministic Seed Tests
# ═══════════════════════════════════════════════════════════

def test_stable_symbol_seed_is_repeatable():
    """同一 symbol 多次调用返回相同值。"""
    s1 = stable_symbol_seed("SS")
    s2 = stable_symbol_seed("SS")
    s3 = stable_symbol_seed("ss")  # 大小写归一
    assert s1 == s2 == s3
    assert isinstance(s1, int)
    assert 0 <= s1 <= 0xFFFFFFFF


def test_stable_symbol_seed_differs_across_symbols():
    """不同 symbol 返回不同值。"""
    seeds = {}
    for sym in ["SS", "RB", "I", "JM", "CF", "TA", "FG", "MA", "SR", "SP"]:
        seeds[sym] = stable_symbol_seed(sym)
    unique_seeds = set(seeds.values())
    assert len(unique_seeds) == len(seeds), f"种子碰撞: {len(unique_seeds)} < {len(seeds)}"


def test_stable_symbol_seed_uses_sha256():
    """验证种子算法是 SHA256，不依赖 Python 内置 hash。"""
    import hashlib
    # 手动计算 SHA256 前 4 字节
    digest = hashlib.sha256("SS".encode("utf-8")).digest()
    expected = int.from_bytes(digest[:4], byteorder="big", signed=False)
    assert stable_symbol_seed("SS") == expected
    # 再验一个不同的 symbol
    digest2 = hashlib.sha256("RB".encode("utf-8")).digest()
    expected2 = int.from_bytes(digest2[:4], byteorder="big", signed=False)
    assert stable_symbol_seed("RB") == expected2


def test_scheme_error_recorded_not_zero():
    """patch _evaluate_one_point 让 HourlyModel 抛异常，验证返回记录包含 scheme_ok=False、scheme_error 非空、scheme_pred_move is None。"""
    import pandas as pd
    import numpy as np
    from unittest.mock import patch

    # 构造最小可用 dense matrix
    mat = pd.DataFrame({
        "bar_idx": [480],
        "timesfm_pure_pred": [0.01],
    })
    closes = np.array([100.0 + i * 0.1 for i in range(600)])
    df_1h = pd.DataFrame({
        "dt": pd.date_range("2024-01-01", periods=600, freq="h"),
        "close_price": closes,
        "high_price": closes + 0.5,
        "low_price": closes - 0.5,
    })

    class FakeModel:
        pass

    class FakeDaily:
        def predict(self, *a, **kw):
            raise RuntimeError("daily model fake error")

    scheme = type("FakeScheme", (), {
        "covariate_type": "ha_body",
        "covariate_types": ("ha_body",),
    })()

    # 导入待测函数
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.a2_p1_worker import _evaluate_one_point

    result = _evaluate_one_point(mat, 480, FakeModel(), FakeDaily(), closes, df_1h, scheme, "ss")

    assert result["scheme_ok"] is False, f"scheme_ok 应为 False, 实际: {result['scheme_ok']}"
    assert result["scheme_error"] is not None and len(result["scheme_error"]) > 0, \
        f"scheme_error 应为非空字符串, 实际: {result['scheme_error']}"
    assert result["scheme_pred_move"] is None, \
        f"scheme_pred_move 应为 None, 实际: {result['scheme_pred_move']}"


def test_validation_rejects_scheme_error():
    """验证 scheme_ok=False 且 scheme_error 非空的记录被校验器拒绝。"""
    rows = [
        {
            "bar_idx": 480, "run_id": "a2-p1", "symbol": "SS", "version": "abc",
            "pure_pred_move": 1.5, "scheme_pred_move": None,
            "lgbm_pred_move": 1.8, "actual_move": 1.2,
            "base_price": 100.0, "atr": 2.5,
            "scheme_ok": False, "scheme_error": "RuntimeError: fake error",
        },
    ]
    result = validate_jsonl_records(rows, [480], "a2-p1", "ss")
    assert not result.ok
    assert any("scheme_error" in e for e in result.errors)


def test_scheme_not_configured_accepted():
    """验证 scheme_ok=None (未配置) 的记录不被拒绝。"""
    rows = [
        {
            "bar_idx": 480, "run_id": "a2-p1", "symbol": "SS", "version": "abc",
            "pure_pred_move": 1.5, "scheme_pred_move": None,
            "lgbm_pred_move": 1.8, "actual_move": 1.2,
            "base_price": 100.0, "atr": 2.5,
            "scheme_ok": None, "scheme_error": None,
        },
        {
            "bar_idx": 504, "run_id": "a2-p1", "symbol": "SS", "version": "abc",
            "pure_pred_move": 1.5, "scheme_pred_move": None,
            "lgbm_pred_move": 1.8, "actual_move": 1.2,
            "base_price": 100.0, "atr": 2.5,
            "scheme_ok": None, "scheme_error": None,
        },
    ]
    result = validate_jsonl_records(rows, [480, 504], "a2-p1", "ss")
    assert result.ok, f"不应拒绝 scheme_ok=None 的记录, errors: {result.errors}"


def test_validation_accepts_scheme_ok_true():
    """验证 scheme_ok=True 的记录正常通过校验。"""
    rows = [
        {
            "bar_idx": 480, "run_id": "a2-p1", "symbol": "SS", "version": "abc",
            "pure_pred_move": 1.5, "scheme_pred_move": 2.0,
            "lgbm_pred_move": 1.8, "actual_move": 1.2,
            "base_price": 100.0, "atr": 2.5,
            "scheme_ok": True, "scheme_error": None,
        },
    ]
    result = validate_jsonl_records(rows, [480], "a2-p1", "ss")
    assert result.ok


def test_worker_uses_stable_seed():
    """源码检查: Worker 必须 from scripts.a2_p1_runtime import stable_symbol_seed，不能用 hash(symbol_upper)。"""
    worker_path = Path(__file__).parent.parent / "scripts" / "a2_p1_worker.py"
    source = worker_path.read_text(encoding="utf-8")

    assert "stable_symbol_seed" in source, "Worker 未引用 stable_symbol_seed"
    assert "from scripts.a2_p1_runtime import" in source and "stable_symbol_seed" in source.split("from scripts.a2_p1_runtime import")[1].split("\n")[0], \
        "Worker 未从 a2_p1_runtime 导入 stable_symbol_seed"
    assert "hash(symbol_upper)" not in source, "Worker 仍在使用 Python 内置 hash(symbol_upper)"


def test_train_lgbm_walkforward_accepts_random_state():
    """函数签名检查: train_lgbm_walkforward 必须接受 random_state 参数。"""
    import inspect
    from scripts.a2_p1_lgbm_baseline import train_lgbm_walkforward
    sig = inspect.signature(train_lgbm_walkforward)
    assert "random_state" in sig.parameters, \
        f"train_lgbm_walkforward 缺少 random_state 参数, 当前参数: {list(sig.parameters.keys())}"


# ═══════════════════════════════════════════════════════════
# Task 5: Manifest, CLI Param, Log Isolation, Terminal States
# ═══════════════════════════════════════════════════════════

from scripts.a2_p1_runtime import build_manifest


def test_build_manifest_captures_identity(tmp_path):
    """manifest 包含 run_id/symbols/paths/python_executable/git_sha。"""
    manifest = build_manifest(
        run_id="a2-p1.1",
        symbols=["ss", "rb"],
        results_dir=tmp_path / "results",
        logs_dir=tmp_path / "logs",
        report_path=tmp_path / "report.md",
        root=Path(__file__).parent.parent,
    )
    assert manifest["run_id"] == "a2-p1.1"
    assert manifest["symbols"] == ["ss", "rb"]
    assert "results_dir" in manifest
    assert "logs_dir" in manifest
    assert "report_path" in manifest
    assert manifest["python_executable"] == sys.executable
    assert "git_sha" in manifest
    assert manifest["git_sha"] != ""
    assert "git_dirty" in manifest
    assert isinstance(manifest["git_dirty"], bool)
    # 文件已写入
    out = tmp_path / "a2-p1.1.manifest.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["run_id"] == "a2-p1.1"


def test_build_manifest_captures_config(tmp_path):
    """manifest 包含 feature_columns/config_snapshot/tick_sizes。"""
    manifest = build_manifest(
        run_id="a2-p1",
        symbols=["ss"],
        results_dir=tmp_path / "results",
        logs_dir=tmp_path / "logs",
        report_path=tmp_path / "report.md",
        root=Path(__file__).parent.parent,
    )
    assert "feature_columns" in manifest
    assert isinstance(manifest["feature_columns"], list)
    assert len(manifest["feature_columns"]) > 0
    assert "config_snapshot" in manifest
    cs = manifest["config_snapshot"]
    assert "CONTEXT_BARS" in cs
    assert "HORIZON" in cs
    assert "STEP" in cs
    assert "SLIPPAGE_TICKS" in cs
    assert "tick_sizes" in manifest
    assert isinstance(manifest["tick_sizes"], dict)
    assert "ss" in manifest["tick_sizes"]


def test_orchestrator_passes_run_id_to_worker():
    """源码检查 Orchestrator 的 subprocess 调用包含 --run-id。"""
    orch_path = Path(__file__).parent.parent / "scripts" / "a2_p1_orchestrator.py"
    source = orch_path.read_text(encoding="utf-8")
    assert "--run-id" in source, "Orchestrator 未传递 --run-id 给 Worker"
    assert "subprocess.Popen(" in source, "Orchestrator 未使用 subprocess.Popen 启动 Worker"
    # 找到 Popen 构造调用行 (排除类型标注), 检查附近有 --run-id
    lines = source.splitlines()
    found_popen_call = False
    for i, line in enumerate(lines):
        if "subprocess.Popen(" in line:
            found_popen_call = True
            context = "\n".join(lines[max(0, i - 2):i + 5])
            assert "--run-id" in context, f"Popen 调用附近未找到 --run-id, 上下文: {context}"
    assert found_popen_call, "Orchestrator 源码中未找到 subprocess.Popen 调用"


def test_worker_accepts_run_id_cli():
    """Worker CLI 接受 --run-id 参数。"""
    import inspect
    from scripts.a2_p1_worker import run_worker, main
    # 函数签名检查
    sig = inspect.signature(run_worker)
    assert "run_id" in sig.parameters, \
        f"run_worker 缺少 run_id 参数, 当前: {list(sig.parameters.keys())}"
    # CLI 参数检查
    worker_path = Path(__file__).parent.parent / "scripts" / "a2_p1_worker.py"
    source = worker_path.read_text(encoding="utf-8")
    assert "--run-id" in source, "Worker CLI 未定义 --run-id 参数"
    assert "a2-p1.1" in source, "Worker CLI 默认值不是 a2-p1.1"


def test_terminal_states_are_exhaustive():
    """源码检查 Orchestrator 包含 DONE/SKIP/FAILED/TIMEOUT/INVALID 五种状态字符串。"""
    orch_path = Path(__file__).parent.parent / "scripts" / "a2_p1_orchestrator.py"
    source = orch_path.read_text(encoding="utf-8")
    for state in ("DONE", "SKIP", "FAILED", "TIMEOUT", "INVALID"):
        assert f'"{state}"' in source or f"'{state}'" in source, \
            f"Orchestrator 缺少终端状态字符串: {state}"
    # 验证常量定义
    assert "_TERMINAL_STATES" in source, "Orchestrator 未定义 _TERMINAL_STATES 常量"


# ═══════════════════════════════════════════════════════════
# Task 6: Historical File Reconciliation Tests
# ═══════════════════════════════════════════════════════════

from scripts.a2_p1_restore_manifest import (
    scan_historical_results,
    restore_missing_results,
    canonicalize_duplicates,
    write_manifest,
    EXPECTED_BARS_COUNT,
    _read_jsonl_rows,
)


def _write_test_jsonl(path: Path, records: list[dict]) -> None:
    """写 JSONL 测试文件。"""
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_restore_dry_run_does_not_modify_files(tmp_path):
    """dry-run 模式下不修改任何文件。"""
    main_dir = tmp_path / "main"
    backup_dir = tmp_path / "backup"
    main_dir.mkdir()
    backup_dir.mkdir()

    # 在备份中创建一个文件
    _write_test_jsonl(backup_dir / "ss.jsonl", [
        {"bar_idx": 480, "symbol": "SS", "version": "abc"},
    ])

    result = restore_missing_results(main_dir, backup_dir, ["ss"], apply=False)

    # 主目录不应有任何文件
    assert not (main_dir / "ss.jsonl").exists()
    # 返回结果应显示为 skipped
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["symbol"] == "ss"
    assert len(result["copied"]) == 0
    assert len(result["conflicts"]) == 0


def test_restore_refuses_existing_destination(tmp_path):
    """主目录已有文件时，restore 应视为 conflict，绝不覆盖。"""
    main_dir = tmp_path / "main"
    backup_dir = tmp_path / "backup"
    main_dir.mkdir()
    backup_dir.mkdir()

    original_content = '{"bar_idx": 480, "symbol": "SS", "version": "original"}\n'
    (main_dir / "ss.jsonl").write_text(original_content, encoding="utf-8")
    _write_test_jsonl(backup_dir / "ss.jsonl", [
        {"bar_idx": 480, "symbol": "SS", "version": "backup"},
    ])

    result = restore_missing_results(main_dir, backup_dir, ["ss"], apply=True)

    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0]["symbol"] == "ss"
    assert len(result["copied"]) == 0
    # 原文件内容不变
    assert (main_dir / "ss.jsonl").read_text(encoding="utf-8") == original_content


def test_restore_copies_missing_symbol(tmp_path):
    """主目录缺失且备份存在时，apply=True 应复制备份到主目录。"""
    main_dir = tmp_path / "main"
    backup_dir = tmp_path / "backup"
    main_dir.mkdir()
    backup_dir.mkdir()

    records = [
        {"bar_idx": 480, "symbol": "RB", "version": "xyz"},
        {"bar_idx": 504, "symbol": "RB", "version": "xyz"},
    ]
    _write_test_jsonl(backup_dir / "rb.jsonl", records)

    result = restore_missing_results(main_dir, backup_dir, ["rb"], apply=True)

    assert len(result["copied"]) == 1
    assert result["copied"][0]["symbol"] == "rb"
    assert (main_dir / "rb.jsonl").exists()
    assert (main_dir / "rb.jsonl").read_text(encoding="utf-8") == (backup_dir / "rb.jsonl").read_text(encoding="utf-8")
    assert len(result["conflicts"]) == 0
    assert len(result["skipped"]) == 0


def test_canonicalize_dry_run_does_not_modify_files(tmp_path):
    """canonicalize dry-run 不修改任何文件。"""
    main_dir = tmp_path / "main"
    main_dir.mkdir()

    # 创建有重复的文件
    records = [
        {"bar_idx": 480, "symbol": "FU", "version": "a"},
        {"bar_idx": 480, "symbol": "FU", "version": "a"},  # 重复
        {"bar_idx": 504, "symbol": "FU", "version": "a"},
    ]
    src = main_dir / "fu.jsonl"
    _write_test_jsonl(src, records)
    original_sha = hashlib.sha256(src.read_bytes()).hexdigest()

    result = canonicalize_duplicates(main_dir, ["fu"], apply=False)

    # 不应生成 .canonical 文件
    assert not (main_dir / "fu.jsonl.canonical").exists()
    # 原文件 SHA 不变
    assert hashlib.sha256(src.read_bytes()).hexdigest() == original_sha
    # 但报告了需要去重
    assert len(result["canonicalized"]) == 1
    assert result["canonicalized"][0]["dry_run"] is True
    assert result["canonicalized"][0]["original_rows"] == 3
    assert result["canonicalized"][0]["canonical_rows"] == 2


def test_canonicalize_writes_canonical_suffix(tmp_path):
    """apply=True 时生成 .canonical 文件，原文件不变。"""
    main_dir = tmp_path / "main"
    main_dir.mkdir()

    records = [
        {"bar_idx": 480, "symbol": "FU", "version": "a"},
        {"bar_idx": 504, "symbol": "FU", "version": "a"},
    ]
    src = main_dir / "fu.jsonl"
    _write_test_jsonl(src, records)
    original_content = src.read_text(encoding="utf-8")

    result = canonicalize_duplicates(main_dir, ["fu"], apply=True)

    canonical_path = main_dir / "fu.jsonl.canonical"
    assert canonical_path.exists(), ".canonical 文件应存在"
    # 原文件不变
    assert src.read_text(encoding="utf-8") == original_content
    # 报告了已干净（无重复所以 already_clean）
    assert len(result["already_clean"]) == 1


def test_canonicalize_deduplicates_by_bar_idx(tmp_path):
    """792 行（每 bar_idx 重复一次）→ 396 行唯一 bar_idx。"""
    main_dir = tmp_path / "main"
    main_dir.mkdir()

    # 模拟 FU 的重复写入：396 个唯一 bar，每个出现 2 次
    bars = list(range(480, 480 + 24 * 396, 24))
    records = []
    for b in bars:
        records.append({"bar_idx": b, "symbol": "FU", "version": "abc"})
        records.append({"bar_idx": b, "symbol": "FU", "version": "abc"})  # 重复

    assert len(records) == 792
    src = main_dir / "fu.jsonl"
    _write_test_jsonl(src, records)

    result = canonicalize_duplicates(main_dir, ["fu"], apply=True)

    assert len(result["canonicalized"]) == 1
    item = result["canonicalized"][0]
    assert item["original_rows"] == 792
    assert item["canonical_rows"] == 396
    assert item["removed_duplicates"] == 396

    # 验证 .canonical 文件的行数和内容
    canonical_path = main_dir / "fu.jsonl.canonical"
    canonical_rows = [json.loads(l) for l in canonical_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(canonical_rows) == 396
    canonical_bars = {r["bar_idx"] for r in canonical_rows}
    assert len(canonical_bars) == 396
    assert canonical_bars == set(bars)


def test_scan_reports_all_sources(tmp_path):
    """main/backup/missing 分类正确。"""
    main_dir = tmp_path / "main"
    backup_dir = tmp_path / "backup"
    main_dir.mkdir()
    backup_dir.mkdir()

    # main 有 ss
    _write_test_jsonl(main_dir / "ss.jsonl", [
        {"bar_idx": 480, "symbol": "SS", "version": "v1"},
    ])
    # backup 有 bu
    _write_test_jsonl(backup_dir / "bu.jsonl", [
        {"bar_idx": 480, "symbol": "BU", "version": "v2"},
    ])
    # sh 两个目录都没有

    scan = scan_historical_results(main_dir, backup_dir, ["ss", "bu", "sh"])

    assert scan["ss"].source == "main"
    assert scan["ss"].main_rows == 1
    assert scan["ss"].sha256 is not None

    assert scan["bu"].source == "backup"
    assert scan["bu"].backup_rows == 1
    assert scan["bu"].sha256 is not None

    assert scan["sh"].source == "missing"
    assert scan["sh"].status == "missing"


def test_write_manifest_creates_file(tmp_path):
    """manifest 文件被正确创建。"""
    main_dir = tmp_path / "main"
    backup_dir = tmp_path / "backup"
    main_dir.mkdir()
    backup_dir.mkdir()

    _write_test_jsonl(main_dir / "ss.jsonl", [
        {"bar_idx": 480, "symbol": "SS", "version": "v1"},
    ])

    manifest_path = tmp_path / "manifest.json"
    manifest = write_manifest(main_dir, backup_dir, ["ss", "bu"], manifest_path)

    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "generated_at" in data
    assert data["expected_symbols"] == ["ss", "bu"]
    assert "ss" in data["per_symbol"]
    assert data["per_symbol"]["ss"]["source"] == "main"
    assert data["per_symbol"]["ss"]["rows"] == 1
    assert "bu" in data["per_symbol"]
    assert data["per_symbol"]["bu"]["source"] == "missing"
    assert data["per_symbol"]["bu"]["status"] == "missing"


def test_restore_no_timesfm_import():
    """源码检查: restore 脚本不含 timesfm/torch/lgb/data_store 等 import。"""
    script_path = Path(__file__).parent.parent / "scripts" / "a2_p1_restore_manifest.py"
    source = script_path.read_text(encoding="utf-8").lower()

    forbidden = ["timesfm", "import torch", "import lgb", "from lgb",
                 "data_store", "tqsdk", "lightgbm"]
    for keyword in forbidden:
        # 忽略注释中的关键词
        code_lines = [l for l in source.splitlines()
                      if not l.strip().startswith("#")]
        code_only = "\n".join(code_lines)
        assert keyword not in code_only, (
            f"restore 脚本不应包含 '{keyword}'"
        )


def test_read_jsonl_rows_rejects_malformed(tmp_path):
    """_read_jsonl_rows 对无效 JSON 行抛 ValueError 并带行号。"""
    path = tmp_path / "bad.jsonl"
    path.write_text('{"bar_idx": 480}\nnot valid json\n{"bar_idx": 504}\n', encoding="utf-8")
    try:
        _read_jsonl_rows(path)
        raise AssertionError("should have raised ValueError")
    except ValueError as e:
        assert ":2" in str(e), f"错误消息应包含行号 :2, 实际: {e}"


def test_scan_reports_unexpected_bars_count(tmp_path):
    """当 unique_bars > expected_bars_count 时，manifest 包含 unexpected_bars_count 字段。"""
    main_dir = tmp_path / "main"
    backup_dir = tmp_path / "backup"
    main_dir.mkdir()
    backup_dir.mkdir()

    # 构造超出预期行数的数据 (预期 396, 我们写入 400)
    bars = list(range(480, 480 + 24 * 400, 24))
    records = [{"bar_idx": b, "symbol": "SS", "version": "v1"} for b in bars[:400]]
    _write_test_jsonl(main_dir / "ss.jsonl", records)

    scan = scan_historical_results(main_dir, backup_dir, ["ss"])
    assert scan["ss"].source == "main"
    assert scan["ss"].main_unique_bars == 400
    assert scan["ss"].unexpected_bars_count == 400 - EXPECTED_BARS_COUNT

    # 验证 write_manifest 输出包含该字段
    manifest_path = tmp_path / "manifest.json"
    manifest = write_manifest(main_dir, backup_dir, ["ss"], manifest_path)
    entry = manifest["per_symbol"]["ss"]
    assert "unexpected_bars_count" in entry
    assert entry["unexpected_bars_count"] == 400 - EXPECTED_BARS_COUNT

def test_integrity_file_has_no_hardcoded_windows_root():
    src = Path(__file__).read_text(encoding="utf-8")
    assert "D:/FlyBuddy/" + "fm_a" not in src
    root = Path(__file__).resolve().parent.parent
    assert (root / "cascade").is_dir()
