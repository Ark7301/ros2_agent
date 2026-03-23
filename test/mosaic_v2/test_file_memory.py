# FileMemory 记忆插件单元测试

import pytest
import pytest_asyncio

from plugins.memory.file_memory import FileMemory, create_plugin
from mosaic.plugin_sdk.types import MemoryEntry, MemoryPlugin, PluginMeta


# ── 工厂函数与协议检查 ──

def test_create_plugin_returns_file_memory():
    """create_plugin 工厂函数应返回 FileMemory 实例"""
    plugin = create_plugin()
    assert isinstance(plugin, FileMemory)


def test_file_memory_satisfies_protocol():
    """FileMemory 应满足 MemoryPlugin Protocol"""
    plugin = create_plugin()
    assert isinstance(plugin, MemoryPlugin)


def test_meta_kind_is_memory():
    """meta.kind 应为 'memory'"""
    plugin = create_plugin()
    assert plugin.meta.kind == "memory"
    assert isinstance(plugin.meta, PluginMeta)


# ── store / get ──

@pytest.mark.asyncio
async def test_store_and_get():
    """存储后应能精确获取"""
    mem = FileMemory()
    await mem.store("k1", "hello world", {"tag": "test"})
    entry = await mem.get("k1")
    assert entry is not None
    assert entry.key == "k1"
    assert entry.content == "hello world"
    assert entry.metadata == {"tag": "test"}


@pytest.mark.asyncio
async def test_get_nonexistent_returns_none():
    """获取不存在的 key 应返回 None"""
    mem = FileMemory()
    assert await mem.get("missing") is None


@pytest.mark.asyncio
async def test_store_overwrites_existing():
    """重复 store 同一 key 应覆盖旧值"""
    mem = FileMemory()
    await mem.store("k1", "old", {})
    await mem.store("k1", "new", {"v": 2})
    entry = await mem.get("k1")
    assert entry is not None
    assert entry.content == "new"
    assert entry.metadata == {"v": 2}


# ── delete ──

@pytest.mark.asyncio
async def test_delete_existing_returns_true():
    """删除存在的 key 应返回 True"""
    mem = FileMemory()
    await mem.store("k1", "data", {})
    assert await mem.delete("k1") is True
    assert await mem.get("k1") is None


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_false():
    """删除不存在的 key 应返回 False"""
    mem = FileMemory()
    assert await mem.delete("nope") is False


# ── search ──

@pytest.mark.asyncio
async def test_search_exact_key_match_highest_score():
    """精确 key 匹配应排在最前"""
    mem = FileMemory()
    await mem.store("apple", "fruit content", {})
    await mem.store("pineapple", "another fruit", {})
    results = await mem.search("apple")
    assert len(results) == 2
    # 精确匹配排第一
    assert results[0].key == "apple"
    assert results[0].score > results[1].score


@pytest.mark.asyncio
async def test_search_content_match():
    """content 包含查询串应被匹配"""
    mem = FileMemory()
    await mem.store("k1", "the quick brown fox", {})
    await mem.store("k2", "lazy dog", {})
    results = await mem.search("quick")
    assert len(results) == 1
    assert results[0].key == "k1"


@pytest.mark.asyncio
async def test_search_no_match():
    """无匹配时应返回空列表"""
    mem = FileMemory()
    await mem.store("k1", "hello", {})
    results = await mem.search("zzz")
    assert results == []


@pytest.mark.asyncio
async def test_search_top_k_limit():
    """search 应遵守 top_k 限制"""
    mem = FileMemory()
    for i in range(10):
        await mem.store(f"item{i}", "common content", {})
    results = await mem.search("common", top_k=3)
    assert len(results) == 3
