import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_schema_v1_accepted():
    from sup_harvest import _ACCEPTED_SCHEMAS
    assert "fm.hypothesis_proposal.v1" in _ACCEPTED_SCHEMAS

def test_schema_v2_accepted():
    from sup_harvest import _ACCEPTED_SCHEMAS
    assert "fm.hypothesis_proposal.v2" in _ACCEPTED_SCHEMAS

def test_schema_v3_rejected():
    from sup_harvest import _ACCEPTED_SCHEMAS
    assert "fm.hypothesis_proposal.v3" not in _ACCEPTED_SCHEMAS

def test_v1_default_version():
    from sup_harvest import _ACCEPTED_SCHEMAS
    assert "fm.hypothesis_proposal.v1" in _ACCEPTED_SCHEMAS

def test_v2_missing_version_rejected():
    from sup_harvest import _check_v2_version
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2"}) == False
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": 2}) == True
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": 0}) == False
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": -1}) == False
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": "abc"}) == False
