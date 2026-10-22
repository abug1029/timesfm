"""B6 多 Role 硬隔离配额测试"""
import yaml
import os
import pytest

ROLES_DIR = "/home/abug/timesfm/task_FM/roles"

def test_momentum_role_exists():
    """momentum role 配置文件存在"""
    path = os.path.join(ROLES_DIR, "family_momentum", "role.yaml")
    assert os.path.exists(path), f"Missing {path}"

def test_volatility_role_exists():
    """volatility role 配置文件存在"""
    path = os.path.join(ROLES_DIR, "family_volatility", "role.yaml")
    assert os.path.exists(path), f"Missing {path}"

def test_momentum_surface_isolation():
    """momentum role 只允许 momentum family"""
    path = os.path.join(ROLES_DIR, "family_momentum", "role.yaml")
    with open(path) as f:
        role = yaml.safe_load(f)
    assert "role" in role
    assert "allowed_surface" in role["role"]
    surface = role["role"]["allowed_surface"]
    assert surface["families"] == ["momentum"]
    assert "volatility" not in surface["families"]

def test_volatility_surface_isolation():
    """volatility role 只允许 volatility family"""
    path = os.path.join(ROLES_DIR, "family_volatility", "role.yaml")
    with open(path) as f:
        role = yaml.safe_load(f)
    assert "role" in role
    assert "allowed_surface" in role["role"]
    surface = role["role"]["allowed_surface"]
    assert surface["families"] == ["volatility"]
    assert "momentum" not in surface["families"]

def test_roles_have_wildcard_symbols():
    """两个 role 都允许所有 symbols"""
    for role_name in ["family_momentum", "family_volatility"]:
        path = os.path.join(ROLES_DIR, role_name, "role.yaml")
        with open(path) as f:
            role = yaml.safe_load(f)
        surface = role["role"]["allowed_surface"]
        assert surface["symbols"] == ["*"]

def test_roles_schema_compliance():
    """role 配置符合 schema_version 1"""
    for role_name in ["family_momentum", "family_volatility"]:
        path = os.path.join(ROLES_DIR, role_name, "role.yaml")
        with open(path) as f:
            role = yaml.safe_load(f)
        assert role["schema_version"] == 1
        assert role["kind"] == "role"
        assert "role_id" in role["role"]
        assert "role_kind" in role["role"]
