#!/usr/bin/env python3
"""Tests for archive_duplicate_proposals.py"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import archive_duplicate_proposals as mod


class TestScanProposals(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.orig_experiments = mod.EXPERIMENTS_DIR
        self.orig_archive = mod.ARCHIVE_DIR
        self.orig_manifest = mod.MANIFEST_PATH
        mod.EXPERIMENTS_DIR = self.tmpdir / "experiments"
        mod.ARCHIVE_DIR = mod.EXPERIMENTS_DIR / "archive"
        mod.MANIFEST_PATH = mod.ARCHIVE_DIR / "archive_manifest.jsonl"

    def tearDown(self):
        mod.EXPERIMENTS_DIR = self.orig_experiments
        mod.ARCHIVE_DIR = self.orig_archive
        mod.MANIFEST_PATH = self.orig_manifest
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_proposal(self, run_id, gen, peer, stem, is_prescreen=False):
        fname = f"{stem}.prescreen.json" if is_prescreen else f"{stem}.json"
        d = mod.EXPERIMENTS_DIR / run_id / "results" / gen / peer / "proposals"
        d.mkdir(parents=True, exist_ok=True)
        (d / fname).write_text("{}")
        return d / fname

    def test_scan_excludes_prescreen(self):
        self._make_proposal("run_001", "gen_0", "peer0", "test_var")
        self._make_proposal("run_001", "gen_0", "peer0", "test_var", is_prescreen=True)
        files = mod.scan_proposals()
        self.assertEqual(len(files), 1)
        self.assertFalse(files[0]["path"].endswith(".prescreen.json"))

    def test_scan_skips_non_run_dirs(self):
        (mod.EXPERIMENTS_DIR / "archive").mkdir(parents=True)
        (mod.EXPERIMENTS_DIR / "archive" / "dummy.json").write_text("{}")
        files = mod.scan_proposals()
        self.assertEqual(len(files), 0)

    def test_scan_extracts_stem_and_run_id(self):
        self._make_proposal("run_2026-01-01_00-00-00_primary", "gen_0", "peer0", "m_vor")
        files = mod.scan_proposals()
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["stem"], "m_vor")
        self.assertEqual(files[0]["run_id"], "run_2026-01-01_00-00-00_primary")


class TestGroupByStem(unittest.TestCase):
    def test_groups_correctly(self):
        files = [
            {"stem": "a", "path": "p1"},
            {"stem": "b", "path": "p2"},
            {"stem": "a", "path": "p3"},
        ]
        groups = mod.group_by_stem(files)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups["a"]), 2)
        self.assertEqual(len(groups["b"]), 1)


class TestPlanArchive(unittest.TestCase):
    def test_keeps_latest_by_mtime(self):
        groups = {
            "var_a": [
                {"stem": "var_a", "mtime": 100, "path": "old"},
                {"stem": "var_a", "mtime": 200, "path": "new"},
                {"stem": "var_a", "mtime": 150, "path": "mid"},
            ]
        }
        to_keep, to_archive = mod.plan_archive(groups)
        self.assertEqual(len(to_keep), 1)
        self.assertEqual(to_keep[0]["path"], "new")
        self.assertEqual(len(to_archive), 2)

    def test_single_file_per_stem_not_archived(self):
        groups = {
            "unique": [{"stem": "unique", "mtime": 100, "path": "only"}]
        }
        to_keep, to_archive = mod.plan_archive(groups)
        self.assertEqual(len(to_keep), 1)
        self.assertEqual(len(to_archive), 0)


class TestExecuteAndRollback(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.orig_experiments = mod.EXPERIMENTS_DIR
        self.orig_archive = mod.ARCHIVE_DIR
        self.orig_manifest = mod.MANIFEST_PATH
        mod.EXPERIMENTS_DIR = self.tmpdir / "experiments"
        mod.ARCHIVE_DIR = mod.EXPERIMENTS_DIR / "archive"
        mod.MANIFEST_PATH = mod.ARCHIVE_DIR / "archive_manifest.jsonl"

    def tearDown(self):
        mod.EXPERIMENTS_DIR = self.orig_experiments
        mod.ARCHIVE_DIR = self.orig_archive
        mod.MANIFEST_PATH = self.orig_manifest
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_proposal(self, run_id, gen, peer, stem, mtime=None):
        d = mod.EXPERIMENTS_DIR / run_id / "results" / gen / peer / "proposals"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{stem}.json"
        p.write_text(json.dumps({"stem": stem}))
        if mtime:
            os.utime(str(p), (mtime, mtime))
        return p

    def test_full_archive_and_rollback_cycle(self):
        p1 = self._make_proposal("run_001", "gen_0", "peer0", "m_vor", mtime=100)
        p2 = self._make_proposal("run_002", "gen_0", "peer0", "m_vor", mtime=200)
        p3 = self._make_proposal("run_003", "gen_0", "peer0", "m_vor", mtime=150)

        mod.do_execute()

        # Only latest (p2, mtime=200) remains
        self.assertTrue(p2.exists())
        self.assertFalse(p1.exists())
        self.assertFalse(p3.exists())

        # Manifest has 2 entries
        self.assertTrue(mod.MANIFEST_PATH.exists())
        lines = [l for l in mod.MANIFEST_PATH.read_text().strip().split("\n") if l]
        self.assertEqual(len(lines), 2)

        # Archive has 2 files
        archived = list(mod.ARCHIVE_DIR.rglob("*.json"))
        self.assertEqual(len(archived), 2)

        # Rollback restores all
        mod.do_rollback()
        self.assertTrue(p1.exists())
        self.assertTrue(p2.exists())
        self.assertTrue(p3.exists())
        self.assertFalse(mod.MANIFEST_PATH.exists())

    def test_prescreen_not_touched(self):
        self._make_proposal("run_001", "gen_0", "peer0", "m_vor", mtime=100)
        ps_dir = mod.EXPERIMENTS_DIR / "run_001" / "results" / "gen_0" / "peer0" / "proposals"
        ps_dir.mkdir(parents=True, exist_ok=True)
        ps_file = ps_dir / "m_vor.prescreen.json"
        ps_file.write_text("{}")

        mod.do_execute()
        self.assertTrue(ps_file.exists())


if __name__ == "__main__":
    unittest.main()
