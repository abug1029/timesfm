"""Task 14: v1 -> v2 verdict 离线迁移脚本测试 (TDD)。

夹具语义:
- ok 行: checkpoint 存在 -> endpoint 指标重算, n_eff==n (STEP=24 迁移语义),
  cov_family=="momentum" (rsi_state), migrated_pass/fdr_pass True
- checkpoint 缺失行: status=="migration_failed", 但仍须通过 validate_verdict (v2 校验)
- 行数守恒: 输出行数 == 输入行数
"""
import importlib.util
import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
for _p in (SCRIPTS, REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from registry_lib import validate_verdict  # noqa: E402
from cascade.evaluation_metrics import fallback_n_eff  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "migrate_verdicts_v1_to_v2",
    os.path.join(SCRIPTS, "migrate_verdicts_v1_to_v2.py"))
mig = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mig)


def _v1_row(**kw):
    row = {
        "schema": "fm.aligned_verdict.v1",
        "variant_id": "m_rsi_state",
        "symbol": "m",
        "cov_override": "rsi_state",
        "stage": "aligned",
        "n": 400,
        "dir_acc": 0.56,
        "gate_pass": True,
        "decided_at": "2026-09-14T09:45:01",
        "git_rev": "abc123",
        "slow_loop_pid": 1,
    }
    row.update(kw)
    return row


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _cp_rows():
    """4 个 checkpoint 点 (base/pred_end/real_end/delta_pred/delta_real/cutoff)。

    期望 (base=1000):
    - endpoint_mape   = mean(|pred_end-real_end|/max(base,1))*100 = 2.25
    - endpoint_bias   = mean((delta_pred-delta_real)/max(base,1))*100 = 0.25
    - dir_acc         = 0.5 (2/4 方向对)
    - weighted_dir_acc = (20+30)/90 = 50/90
    """
    return [
        {"cutoff": "2025-12-22", "base": 1000.0, "pred_end": 1010.0, "real_end": 1020.0,
         "delta_pred": 10.0, "delta_real": 20.0},
        {"cutoff": "2025-12-23", "base": 1000.0, "pred_end": 990.0, "real_end": 970.0,
         "delta_pred": -10.0, "delta_real": -30.0},
        {"cutoff": "2025-12-24", "base": 1000.0, "pred_end": 1010.0, "real_end": 980.0,
         "delta_pred": 10.0, "delta_real": -20.0},
        {"cutoff": "2025-12-25", "base": 1000.0, "pred_end": 990.0, "real_end": 1020.0,
         "delta_pred": -10.0, "delta_real": 20.0},
    ]


# ── 主夹具: ok 行 + checkpoint 缺失行 ──

def test_migrate_ok_and_failed_and_n_eff(tmp_path):
    cp = tmp_path / "cp_ok.jsonl"
    _write_jsonl(cp, _cp_rows())
    ok_row = _v1_row(checkpoint_path=str(cp))
    failed_row = _v1_row(variant_id="m_missing_cp", cov_override="rsi_slope",
                         checkpoint_path=str(tmp_path / "nope.jsonl"))
    src = tmp_path / "v1.jsonl"
    dst = tmp_path / "v2.jsonl"
    _write_jsonl(src, [ok_row, failed_row])

    rc = mig.main(["--src", str(src), "--dst", str(dst)])
    assert rc == 0

    with open(dst, encoding="utf-8") as f:
        out = [json.loads(l) for l in f if l.strip()]
    assert len(out) == 2  # 行数守恒
    by_id = {r["variant_id"]: r for r in out}

    ok = by_id["m_rsi_state"]
    assert ok["schema"] == "fm.aligned_verdict.v2"
    assert ok["batch_id"] == "migrated_v1"
    assert ok["status"] == "ok"
    assert ok["n"] == 400
    assert ok["n_eff"] == 400  # v1 缺 n_eff -> fallback_n_eff(n, HORIZON=24, STEP=24) == n
    assert ok["cov_family"] == "momentum"
    assert ok["migrated_pass"] is True
    assert ok["fdr_pass"] is True
    assert ok["gate_pass"] is True
    assert ok["endpoint_mape"] == pytest.approx(2.25)
    assert ok["endpoint_bias_pct"] == pytest.approx(0.25)
    assert ok["weighted_dir_acc"] == pytest.approx(50.0 / 90.0)
    assert ok["dir_acc"] == 0.56  # v1 已有 dir_acc -> 不用 checkpoint 重算覆盖
    assert ok["path_corr"] is None
    assert ok["p_value"] is None
    assert validate_verdict(ok) == []

    failed = by_id["m_missing_cp"]
    assert failed["status"] == "migration_failed"
    assert failed["endpoint_mape"] is None
    assert failed["weighted_dir_acc"] == 0.0
    assert failed["migrated_pass"] is False  # M1: 墓碑约定, fdr/migrated 强制 False
    assert failed["fdr_pass"] is False
    assert failed["gate_pass"] is True  # gate_pass 保留新 gate 重判值
    assert validate_verdict(failed) == []  # 墓碑字段兜底齐全


# ── 补充: migration_failed 行必须过 v2 校验 (单独覆盖) ──

def test_migration_failed_row_passes_validate(tmp_path):
    rec = _v1_row(checkpoint_path=str(tmp_path / "missing.jsonl"))
    out = mig.migrate_row(rec, mig._load_gate())
    assert out["status"] == "migration_failed"
    assert out["error_message"]
    assert validate_verdict(out) == []
    # metrics 子字典镜像 (make_error_tombstone 兜底方式)
    assert isinstance(out["metrics"], dict)
    assert out["metrics"]["status"] == "migration_failed"
    assert out["metrics"]["n"] == out["n"]


# ── 补充: v1 缺 n_eff 时 fallback_n_eff(n, 24, 24) == n 语义 ──

def test_fallback_n_eff_step24_semantics(tmp_path):
    # STEP=24 网格 (step >= horizon) 不产生重叠 -> n_eff == n
    for n in (1, 100, 350, 400, 1000):
        assert fallback_n_eff(n, 24, 24) == n
    cp = tmp_path / "cp_neff_fb.jsonl"
    _write_jsonl(cp, _cp_rows())
    rec = _v1_row(n=360, checkpoint_path=str(cp))  # checkpoint 可读 -> status=ok, 隔离 fallback 语义
    rec.pop("n_eff", None)
    out = mig.migrate_row(rec, mig._load_gate())
    assert out["status"] == "ok"
    assert out["n_eff"] == 360
    assert validate_verdict(out) == []


# ── 补充: v1 原始 gate_pass=False 时 migrated_pass/fdr_pass 必为 False ──

def test_v1_gate_false_never_migrated_pass(tmp_path):
    cp = tmp_path / "cp_gatefalse.jsonl"
    _write_jsonl(cp, _cp_rows())
    # 新 gate 会过 (n=400, dir_acc=0.56), 但 v1 未过; checkpoint 可读保持 status=ok, 隔离 v1_gate 因素
    rec = _v1_row(gate_pass=False, checkpoint_path=str(cp))
    out = mig.migrate_row(rec, mig._load_gate())
    assert out["status"] == "ok"
    assert out["gate_pass"] is True
    assert out["migrated_pass"] is False
    assert out["fdr_pass"] is False
    assert validate_verdict(out) == []


# ── 补充: CLI 守卫 -- dst 等于 src 拒绝 (防原地覆盖) ──

def test_cli_refuses_same_src_dst(tmp_path):
    src = tmp_path / "v1.jsonl"
    _write_jsonl(src, [_v1_row()])
    with pytest.raises(SystemExit):
        mig.main(["--src", str(src), "--dst", str(src)])
    # 未产出任何 tmp 残留, 原文件未动
    assert list(tmp_path.glob("*.tmp")) == []
    with open(src, encoding="utf-8") as f:
        assert len([l for l in f if l.strip()]) == 1


# ── 补充: checkpoint 中 error 行/缺字段行跳过, 全坏 checkpoint 判 failed ──

def test_checkpoint_error_rows_skipped(tmp_path):
    cp = tmp_path / "cp_mixed.jsonl"
    rows = _cp_rows() + [{"symbol": "m", "idx": 1, "error": "boom", "cutoff": "x"},
                         {"cutoff": "y", "base": 1000.0}]  # 缺 pred_end/real_end
    _write_jsonl(cp, rows)
    out = mig.migrate_row(_v1_row(checkpoint_path=str(cp)), mig._load_gate())
    assert out["status"] == "ok"
    assert out["endpoint_mape"] == pytest.approx(2.25)

    cp_bad = tmp_path / "cp_allbad.jsonl"
    _write_jsonl(cp_bad, [{"symbol": "m", "idx": 2, "error": "boom"}])
    out_bad = mig.migrate_row(_v1_row(checkpoint_path=str(cp_bad)), mig._load_gate())
    assert out_bad["status"] == "migration_failed"
    assert validate_verdict(out_bad) == []


# ── M2: v1 行缺 checkpoint_path 字段 (键不存在或 None) -> migration_failed ──

def test_missing_checkpoint_path_field_is_failed():
    rec = _v1_row()
    rec.pop("checkpoint_path", None)  # 键不存在
    out = mig.migrate_row(rec, mig._load_gate())
    assert out["status"] == "migration_failed"
    assert out["error_message"] == "checkpoint_path field missing"
    # 指标全空 (墓碑兜底), 但仍过 v2 校验
    assert out["endpoint_mape"] is None
    assert out["endpoint_bias_pct"] is None
    assert out["weighted_dir_acc"] == 0.0
    assert validate_verdict(out) == []

    out_none = mig.migrate_row(_v1_row(checkpoint_path=None), mig._load_gate())
    assert out_none["status"] == "migration_failed"
    assert out_none["error_message"] == "checkpoint_path field missing"


# ── M1: failed 行 fdr_pass/migrated_pass 强制 False (即使 v1/新 gate 双 True) ──

def test_failed_row_forces_fdr_and_migrated_pass_false(tmp_path):
    cp = tmp_path / "cp_m1.jsonl"
    _write_jsonl(cp, _cp_rows())
    # v1 gate_pass=True, 新 gate 也过 (n=400, dir_acc=0.56), 但 checkpoint 缺失 -> failed
    rec = _v1_row(checkpoint_path=str(tmp_path / "nope_m1.jsonl"))
    out = mig.migrate_row(rec, mig._load_gate())
    assert out["status"] == "migration_failed"
    assert out["gate_pass"] is True  # gate_pass 保留新 gate 重判值
    assert out["migrated_pass"] is False
    assert out["fdr_pass"] is False
    assert validate_verdict(out) == []


# ── M3: v1 gate_pass=True 但新 gate 不过 -> migrated_pass 显式 False ──

def test_v1_gate_true_new_gate_fail_migrated_pass_false(tmp_path):
    cp = tmp_path / "cp_m3a.jsonl"
    _write_jsonl(cp, _cp_rows())
    rec = _v1_row(n=400, n_eff=71, dir_acc=0.50, checkpoint_path=str(cp))
    out = mig.migrate_row(rec, mig._load_gate())
    assert out["status"] == "ok"  # checkpoint 可读, 隔离新 gate 因素
    assert out["gate_pass"] is False  # dir_acc 0.50 < 0.52, 新 gate 不过
    assert out["migrated_pass"] is False
    assert out["fdr_pass"] is False
    assert validate_verdict(out) == []


# ── M3: v1 行自带 n_eff=71 -> 保留 71, 不 fallback ──

def test_v1_n_eff_71_preserved_no_fallback(tmp_path):
    cp = tmp_path / "cp_m3b.jsonl"
    _write_jsonl(cp, _cp_rows())
    rec = _v1_row(n=400, n_eff=71, checkpoint_path=str(cp))
    out = mig.migrate_row(rec, mig._load_gate())
    assert out["status"] == "ok"
    assert out["n_eff"] == 71  # 不 fallback 到 fallback_n_eff(400, 24, 24) == 400
    assert validate_verdict(out) == []


# ── L4: checkpoint 非 UTF-8 -> migration_failed, 不崩溃 ──

def test_non_utf8_checkpoint_failed_not_crash(tmp_path):
    cp = tmp_path / "cp_bin.jsonl"
    cp.write_bytes(b"\xff\xfe{\n")  # 非法 UTF-8
    out = mig.migrate_row(_v1_row(checkpoint_path=str(cp)), mig._load_gate())
    assert out["status"] == "migration_failed"
    assert "checkpoint 不可读" in out["error_message"]
    assert validate_verdict(out) == []


# ── L5: Δp==0 方向归错 (与 sign() 口径等价) ──

def test_zero_delta_pred_counts_wrong_direction(tmp_path):
    cp = tmp_path / "cp_zero.jsonl"
    _write_jsonl(cp, [
        {"cutoff": "a", "base": 1000.0, "pred_end": 1000.0, "real_end": 1010.0,
         "delta_pred": 0.0, "delta_real": 10.0},
    ])
    rec = _v1_row(dir_acc=None, checkpoint_path=str(cp))  # dir_acc 缺 -> 用 checkpoint 重算
    out = mig.migrate_row(rec, mig._load_gate())
    assert out["status"] == "ok"
    assert out["dir_acc"] == 0.0        # Δp==0 判错, 0/1
    assert out["weighted_dir_acc"] == 0.0


# ── L6: main 中止路径清理 tmp 残留 (dst 不受影响) ──

def test_cli_abort_cleans_tmp_on_invalid_json(tmp_path):
    src = tmp_path / "v1.jsonl"
    dst = tmp_path / "v2.jsonl"
    _write_jsonl(src, [_v1_row(checkpoint_path=str(tmp_path / "missing.jsonl"))])
    with open(src, "a", encoding="utf-8") as f:
        f.write("{bad json\n")  # 第 2 行非法 JSON -> 中止
    with pytest.raises(SystemExit):
        mig.main(["--src", str(src), "--dst", str(dst)])
    assert not dst.exists()  # dst 未被写入
    assert list(tmp_path.glob("*.tmp")) == []  # tmp 已清理


# ── L7: _load_pool 失败降级时向 stderr 打警告 ──

def test_load_pool_failure_warns_stderr(monkeypatch, capsys):
    def boom():
        raise RuntimeError("pool down")
    monkeypatch.setattr(mig, "load_covariate_pool", boom)
    pool = mig._load_pool()
    captured = capsys.readouterr()
    assert pool == {"covariates": []}
    assert "协变量池" in captured.err
