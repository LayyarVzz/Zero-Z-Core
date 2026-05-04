"""长期记忆 — JSON 文件持久化，支持关键词检索。"""

import datetime
import json
from pathlib import Path
from typing import Any

from core.config import ROOT


class LongTermMemory:
    """长期记忆存储，JSON 文件读写，支持增/查/最近 N 条。

    设计为简单的 key-value 结构，每条记录附带时间戳。
    最多保留 50 条，超出自动淘汰最旧的。
    """

    def __init__(self, path: str = "data/memory.json") -> None:
        filepath = Path(path)
        # 相对路径基于项目根目录 ROOT 补全
        if not filepath.is_absolute():
            filepath = ROOT / filepath
        self._path = filepath
        self._entries: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """从 JSON 文件加载已有记忆，文件不存在则初始化为空列表。"""
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                try:
                    self._entries = json.load(f)
                except json.JSONDecodeError:
                    print(f"[Memory] 记忆文件损坏，从空开始")
                    self._entries = []
        else:
            self._entries = []

    def _save(self) -> None:
        """持久化到 JSON 文件，ensure_ascii=False 保留中文可读性。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, ensure_ascii=False, indent=2)

    def add(self, key: str, value: str) -> None:
        """新增一条记忆，自动附加时间戳。超过 50 条保留最新 50 条。"""
        self._entries.append({"key": key, "value": value, "timestamp": self._now()})
        # 滑动窗口：只保留最新 50 条，旧数据自动丢弃
        if len(self._entries) > 50:
            self._entries = self._entries[-50:]
        self._save()

    def search(self, query: str) -> list[str]:
        """关键词搜索记忆条目，在 key 和 value 中匹配，返回最近 5 条。"""
        results = []
        for entry in reversed(self._entries):  # 从新到旧遍历
            if query in entry["key"] or query in entry["value"]:
                results.append(f"{entry['key']}: {entry['value']}")
        return results[:5]  # 取前 5 条（即最新的 5 条）

    def recent(self, n: int = 10) -> list[dict[str, Any]]:
        """返回最近 n 条原始记录，供上层组装 LLM 上下文。"""
        return self._entries[-n:]

    @staticmethod
    def _now() -> str:
        """当前时间的 ISO 格式字符串。"""
        return datetime.datetime.now().isoformat()
