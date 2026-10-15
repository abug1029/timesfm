import sys
from pathlib import Path

# 让 tests/ 下的脚本可以直接 import scripts.* 和顶层包
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# sup_evidence.py 等 scripts/ 下的模块用 bare import（如 import registry_lib）
# 需要把 scripts/ 也加到 sys.path
_scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: 真模型/真数据集成测试 (分钟级), 常规回归用 -m 'not slow' 排除")
