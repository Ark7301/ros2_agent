# 文件记忆插件
# 基于内存字典的简单记忆存储，支持子串匹配搜索

from __future__ import annotations

from typing import Any

from mosaic.plugin_sdk.types import MemoryEntry, MemoryPlugin, PluginMeta


class FileMemory:
    """文件记忆插件

    使用内存字典存储 MemoryEntry，search 基于子串匹配，
    排序规则：key 精确匹配优先，content 匹配次之。
    """

    def __init__(self) -> None:
        self.meta = PluginMeta(
            id="file-memory",
            name="File Memory",
            version="0.1.0",
            description="基于内存字典的简单记忆插件，支持子串匹配搜索",
            kind="memory",
            author="MOSAIC",
        )
        # 内存存储：key → MemoryEntry
        self._entries: dict[str, MemoryEntry] = {}

    async def store(self, key: str, content: str, metadata: dict) -> None:
        """存储或更新一条记忆"""
        self._entries[key] = MemoryEntry(
            key=key,
            content=content,
            metadata=metadata,
        )

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """子串匹配搜索

        匹配规则：query 出现在 key 或 content 中。
        排序：key 精确匹配 score=2.0，key 包含 score=1.5，
              content 包含 score=1.0。取 top_k 条。
        """
        results: list[MemoryEntry] = []

        for entry in self._entries.values():
            score = 0.0
            if query == entry.key:
                # key 精确匹配，最高优先
                score = 2.0
            elif query in entry.key:
                # key 包含查询串
                score = 1.5
            elif query in entry.content:
                # content 包含查询串
                score = 1.0

            if score > 0:
                # 创建带分数的副本
                results.append(MemoryEntry(
                    key=entry.key,
                    content=entry.content,
                    metadata=entry.metadata,
                    score=score,
                ))

        # 按 score 降序排列，取 top_k
        results.sort(key=lambda e: e.score, reverse=True)
        return results[:top_k]

    async def get(self, key: str) -> MemoryEntry | None:
        """按 key 精确获取记忆条目"""
        return self._entries.get(key)

    async def delete(self, key: str) -> bool:
        """删除记忆条目，返回是否存在并被删除"""
        if key in self._entries:
            del self._entries[key]
            return True
        return False


def create_plugin() -> FileMemory:
    """工厂函数 — 返回 FileMemory 实例"""
    return FileMemory()
