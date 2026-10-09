"""Tests for maintenance flag expiry in diagnose_three_loop.sh.

closure spec 4.1.3: T_expire = 4 hours.
Flag mtime < 4h -> self-heal disabled (maintenance window active).
Flag mtime >= 4h -> flag expired, self-heal resumes.
"""
import os
import subprocess
import time
from pathlib import Path

import pytest

FM_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = FM_ROOT / "scripts" / "diagnose_three_loop.sh"


def _run_with_flag(flag_age_seconds):
    """Create a maintenance flag with given age, run script, return stdout."""
    cache_dir = FM_ROOT / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    flag_path = cache_dir / "maintenance.flag"

    now = int(time.time())
    flag_mtime = now - flag_age_seconds

    try:
        flag_path.touch()
        os.utime(str(flag_path), (flag_mtime, flag_mtime))

        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(FM_ROOT),
        )
        return result.stdout + result.stderr
    finally:
        flag_path.unlink(missing_ok=True)


class TestMaintFlagExpiry:
    """Maintenance flag expiry = 4 hours (closure spec 4.1.3)."""

    def test_flag_3h_old__window_active(self):
        """Flag mtime = 3 hours ago -> not expired -> self-heal disabled."""
        output = _run_with_flag(3 * 3600)
        assert "MAINTENANCE" in output or "维护窗口激活" in output,             f"Expected window active, got: {output}"

    def test_flag_5h_old__window_expired(self):
        """Flag mtime = 5 hours ago -> expired -> self-heal resumes."""
        output = _run_with_flag(5 * 3600)
        assert "维护窗口已过期" in output,             f"Expected window expired, got: {output}"

    def test_flag_1h_old__window_active(self):
        """Flag mtime = 1 hour ago -> not expired."""
        output = _run_with_flag(1 * 3600)
        assert "MAINTENANCE" in output or "维护窗口激活" in output,             f"Expected window active, got: {output}"

    def test_constant_is_4_hours(self):
        """Verify the constant is defined as 4 hours, not 7 days."""
        content = SCRIPT.read_text()
        assert "MAINT_FLAG_EXPIRE_HOURS=4" in content
        assert "MAINT_FLAG_EXPIRE_DAYS" not in content
