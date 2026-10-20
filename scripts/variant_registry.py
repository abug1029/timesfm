"""
全局 variant 登记（写盘前检查）

维护 variant_registry.jsonl，记录所有已处理的 variant_id (stem)。
harvest 扫描提案文件前，先查询 registry，跳过已注册的 stem。

Registry 格式（JSONL）：
{"stem": "p_calendar_cyclical", "first_seen": "ISO timestamp", "run_id": "..."}

用法：
    registry = VariantRegistry(registry_path)
    registry.load()  # 启动时加载已有 registry

    # 写盘前检查
    if registry.has_stem(stem):
        # 已存在，跳过写盘
        pass
    else:
        # 新 stem，写盘后注册
        registry.register(stem, run_id)
"""
import contextlib
import fcntl
import json
import os
from datetime import datetime, timezone
from typing import Optional


@contextlib.contextmanager
def _registry_lock(path):
    """侧车锁，对齐 proposal_status.jsonl 的锁模式。"""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    lock = open(path + ".lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


class VariantRegistry:
    """全局 variant 登记管理器。"""

    def __init__(self, registry_path: str):
        self.registry_path = registry_path
        self._stems: dict[str, dict] = {}

    def load(self) -> int:
        """加载已有 registry，返回已加载的 stem 数量。"""
        if not os.path.exists(self.registry_path):
            return 0
        count = 0
        with _registry_lock(self.registry_path):
            for line in open(self.registry_path, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    stem = rec.get("stem")
                    if stem:
                        self._stems[stem] = rec
                        count += 1
                except json.JSONDecodeError:
                    continue
        return count

    def has_stem(self, stem: str) -> bool:
        """检查 stem 是否已注册。"""
        return stem in self._stems

    def register(self, stem: str, run_id: str, ts: Optional[str] = None) -> None:
        """注册新 stem（append-only，幂等）。"""
        if stem in self._stems:
            return
        if ts is None:
            ts = datetime.now(timezone.utc).isoformat()
        record = {"stem": stem, "first_seen": ts, "run_id": run_id}
        with _registry_lock(self.registry_path):
            if stem in self._stems:
                return
            parent = os.path.dirname(self.registry_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(self.registry_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._stems[stem] = record

    def get_stems(self) -> set[str]:
        """返回所有已注册的 stem 集合。"""
        return set(self._stems.keys())

    def __len__(self) -> int:
        return len(self._stems)
