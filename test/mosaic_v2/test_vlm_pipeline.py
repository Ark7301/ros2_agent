# test/mosaic_v2/test_vlm_pipeline.py
"""VLM 语义地图管道 — 属性测试

使用 hypothesis 对 VLMAnalyzer 的纯函数进行属性基测试：
- Property 1: VLM 响应解析完整性
- Property 2: 非法 JSON 返回空结果
- Property 3: 场景上下文注入 prompt
"""

from __future__ import annotations

import json

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from mosaic.runtime.vlm_pipeline.vlm_analyzer import VLMAnalyzer, _VALID_CATEGORIES


# ── 辅助策略 ──

# 生成有效物体字典的策略
_valid_object_strategy = st.fixed_dictionaries({
    "label": st.text(min_size=1, max_size=30).filter(lambda s: s.strip() != ""),
    "category": st.sampled_from(sorted(_VALID_CATEGORIES)),
    "bbox": st.lists(st.integers(min_value=0, max_value=2000), min_size=4, max_size=4),
})

# 生成无效物体字典的策略（可能缺少 label、bbox 长度不对等）
_invalid_object_strategy = st.one_of(
    # label 为空字符串
    st.fixed_dictionaries({
        "label": st.just(""),
        "category": st.sampled_from(sorted(_VALID_CATEGORIES)),
        "bbox": st.lists(st.integers(min_value=0, max_value=2000), min_size=4, max_size=4),
    }),
    # bbox 长度不为 4
    st.fixed_dictionaries({
        "label": st.text(min_size=1, max_size=10),
        "category": st.sampled_from(sorted(_VALID_CATEGORIES)),
        "bbox": st.lists(st.integers(min_value=0, max_value=2000), min_size=0, max_size=3),
    }),
    # 非 dict 类型
    st.just("not_a_dict"),
    st.just(42),
    st.just(None),
)

# 生成完整有效 VLM JSON 响应的策略
_valid_vlm_response_strategy = st.fixed_dictionaries({
    "objects": st.lists(_valid_object_strategy, min_size=0, max_size=10),
    "room_type": st.text(min_size=1, max_size=20),
    "room_confidence": st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
})

# 生成混合有效+无效物体的 VLM JSON 响应策略
_mixed_vlm_response_strategy = st.fixed_dictionaries({
    "objects": st.lists(
        st.one_of(_valid_object_strategy, _invalid_object_strategy),
        min_size=0,
        max_size=10,
    ),
    "room_type": st.text(min_size=1, max_size=20),
    "room_confidence": st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
})


def _count_valid_objects(objects: list) -> int:
    """计算列表中有效物体的数量（与 VLMAnalyzer._parse_objects 逻辑一致）"""
    count = 0
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        label = str(obj.get("label", ""))
        if not label:
            continue
        bbox = obj.get("bbox", [0, 0, 0, 0])
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        # bbox 值必须可转为整数（不会抛 ValueError/TypeError）
        try:
            _ = [int(b) for b in bbox]
        except (ValueError, TypeError):
            continue
        count += 1
    return count


# ── Property 1: VLM 响应解析完整性 ──
# **Validates: Requirements 1.1, 1.2**


@given(data=_valid_vlm_response_strategy)
@settings(max_examples=200)
def test_property1_parse_response_valid_object_count(data: dict) -> None:
    """Property 1: 对所有包含有效 objects 数组和 room_type 字段的 JSON 字符串，
    解析后 DetectionResult 中物体数量等于输入 JSON 中有效物体数量。
    """
    raw_json = json.dumps(data, ensure_ascii=False)
    analyzer = VLMAnalyzer()
    result = analyzer._parse_response(raw_json)

    expected_count = len(data["objects"])  # 全部是有效物体
    assert len(result.objects) == expected_count, (
        f"期望 {expected_count} 个物体，实际解析出 {len(result.objects)} 个"
    )


@given(data=_mixed_vlm_response_strategy)
@settings(max_examples=200)
def test_property1_parse_response_mixed_object_count(data: dict) -> None:
    """Property 1 补充: 混合有效/无效物体时，解析数量等于有效物体数量。"""
    raw_json = json.dumps(data, ensure_ascii=False)
    analyzer = VLMAnalyzer()
    result = analyzer._parse_response(raw_json)

    expected_count = _count_valid_objects(data["objects"])
    assert len(result.objects) == expected_count, (
        f"期望 {expected_count} 个有效物体，实际解析出 {len(result.objects)} 个"
    )


# ── Property 2: 非法 JSON 返回空结果 ──
# **Validates: Requirements 1.4**


@given(raw=st.text(min_size=0, max_size=500))
@settings(max_examples=200)
def test_property2_invalid_json_returns_empty(raw: str) -> None:
    """Property 2: 对所有非法 JSON 字符串，解析后返回空 DetectionResult，不抛异常。"""
    # 过滤掉恰好是合法 JSON 的字符串
    try:
        json.loads(raw)
        assume(False)  # 跳过合法 JSON
    except (json.JSONDecodeError, ValueError):
        pass

    analyzer = VLMAnalyzer()
    result = analyzer._parse_response(raw)

    assert len(result.objects) == 0, "非法 JSON 应返回空物体列表"
    assert result.room_classification is None, "非法 JSON 应返回空房间分类"


# ── Property 3: 场景上下文注入 prompt ──
# **Validates: Requirements 1.5**


@given(scene_context=st.text(min_size=1, max_size=500))
@settings(max_examples=200)
def test_property3_scene_context_in_prompt(scene_context: str) -> None:
    """Property 3: 对所有非空 scene_context，构建的 prompt 包含该文本。"""
    analyzer = VLMAnalyzer()
    prompt = analyzer._build_prompt(scene_context)

    assert scene_context in prompt, (
        f"scene_context '{scene_context[:50]}...' 未出现在 prompt 中"
    )
