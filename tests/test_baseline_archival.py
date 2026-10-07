"""步① 基线快照版本化测试（2026-10-07 裁定 A.8，事项一五步之第 1 步）。

重生即归档：gbp.generate() 覆盖旧档前，先复制为带锚定日的归档副本。
锚定日 = 旧档最后一个可解析行的 cutoff（评估窗末端）；全坏回退文件 mtime。
归档 = copy 语义（原档留给 generate 覆盖）；归档失败仅 WARN 不阻塞重生。
"""
import json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import praxist_supervisor as sup


def _write_points(path, cutoffs, fp="fp_test"):
    with open(path, "w", encoding="utf-8") as f:
        for c in cutoffs:
            f.write(json.dumps({"cutoff": c, "dir_ok": True, "delta_pred": 1.0,
                                "delta_real": 1.0, "protocol_fingerprint": fp}) + "\n")


def test_archive_creates_copy_with_anchor_date(tmp_path):
    pts = tmp_path / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, ["2025-09-26 10:00:00", "2025-09-30 14:00:00"])
    before = pts.read_bytes()
    archive = sup._archive_baseline_before_regen(str(pts))
    assert archive is not None
    assert os.path.basename(archive) == "baseline_points_jd_nocov.archive_20250930T1400.jsonl"
    with open(archive, "rb") as f:
        assert f.read() == before      # 归档逐字节一致
    assert pts.read_bytes() == before  # 原档未动（copy 语义）


def test_archive_skips_missing(tmp_path):
    assert sup._archive_baseline_before_regen(str(tmp_path / "nope.jsonl")) is None


def test_archive_collision_appends_counter(tmp_path):
    pts = tmp_path / "baseline_points_sr_nocov.jsonl"
    _write_points(pts, ["2025-09-30 14:00:00"])
    a1 = sup._archive_baseline_before_regen(str(pts))
    a2 = sup._archive_baseline_before_regen(str(pts))
    assert a1 != a2
    assert os.path.basename(a2).endswith("_1.jsonl")


def test_archive_uses_last_parseable_line_then_mtime_fallback(tmp_path):
    pts = tmp_path / "baseline_points_cf_nocov.jsonl"
    # 首行可解析、尾行坏 → 锚 = 最后可解析行 cutoff
    pts.write_text(
        json.dumps({"cutoff": "2025-09-26 10:00:00", "dir_ok": True,
                    "delta_pred": 1.0, "delta_real": 1.0,
                    "protocol_fingerprint": "fp"}) + "\n{broken\n",
        encoding="utf-8")
    archive = sup._archive_baseline_before_regen(str(pts))
    assert os.path.basename(archive) == "baseline_points_cf_nocov.archive_20250926T1000.jsonl"

    # 全坏 → 回退 mtime
    pts2 = tmp_path / "baseline_points_eg_nocov.jsonl"
    pts2.write_text("not json at all\n", encoding="utf-8")
    os.utime(pts2, (1750000000, 1750000000))
    ts = datetime.fromtimestamp(1750000000).strftime("%Y%m%dT%H%M")
    archive2 = sup._archive_baseline_before_regen(str(pts2))
    assert os.path.basename(archive2) == f"baseline_points_eg_nocov.archive_{ts}.jsonl"


class _FakeGbp:
    def __init__(self):
        self.calls = []

    def baseline_filename(self, sym, cov):
        return f"baseline_points_{sym}_nocov.jsonl"

    def generate(self, sym, cov, root):
        self.calls.append((sym, cov, root))


def test_ensure_baselines_archives_before_regen(tmp_path, monkeypatch):
    """指纹不符触发重生时，旧档必须先被归档（三重生点共享同一插桩）。"""
    config_dir = tmp_path / "task_FM" / "config"
    config_dir.mkdir(parents=True)
    metrics = {"jd": {"n": 588, "dir_acc": 0.5, "endpoint_mape": 1.0, "n_eff": 73}}
    (config_dir / "baseline_metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    pts = config_dir / "baseline_points_jd_nocov.jsonl"
    _write_points(pts, ["2025-09-30 14:00:00"] * 150, fp="fp_old")

    fake = _FakeGbp()
    monkeypatch.setitem(sys.modules, "generate_baseline_points", fake)
    monkeypatch.setattr(sup, "_current_protocol_fingerprint", lambda: "fp_cur")

    sup.ensure_baselines(["JD"], str(tmp_path))

    assert len(fake.calls) == 1  # 行数足、指纹不符 → 重生一次
    archives = list(config_dir.glob("baseline_points_jd_nocov.archive_*.jsonl"))
    assert len(archives) == 1
    assert os.path.basename(archives[0]) == "baseline_points_jd_nocov.archive_20250930T1400.jsonl"
