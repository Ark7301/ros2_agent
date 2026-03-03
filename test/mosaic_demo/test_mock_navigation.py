"""
MockNavigationCapability 属性测试

Property 18: 成功结果包含地名
对于任意已注册的地名，MockNavigationCapability 执行 navigate_to 后
返回的 ExecutionResult 的 message 应包含该地名。

**Validates: Requirements 6.3**
"""

import asyncio
import pytest
from hypothesis import given, strategies as st, settings

from mosaic_demo.capabilities.location_service import LocationService
from mosaic_demo.capabilities.mock_navigation import MockNavigationCapability
from mosaic_demo.interfaces_abstract.data_models import Task


# 生成合法的中文/英文地名策略
location_name_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),  # 字母和数字
    ),
    min_size=1,
    max_size=20,
).filter(lambda s: s.strip() != "")

# 生成坐标策略
coords_strategy = st.fixed_dictionaries({
    "x": st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    "y": st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    "theta": st.floats(min_value=-3.15, max_value=3.15, allow_nan=False, allow_infinity=False),
})


@given(name=location_name_strategy, coords=coords_strategy)
@settings(max_examples=50, deadline=None)
def test_navigate_to_success_message_contains_location_name(name, coords):
    """Property 18: 成功结果包含地名

    **Validates: Requirements 6.3**

    对于任意已注册的地名，MockNavigationCapability 执行 navigate_to 后
    返回的 ExecutionResult 的 message 应包含该地名。
    """
    # 创建 LocationService 并注册地名
    location_service = LocationService()
    location_service.add_location(name, coords)

    # 创建 MockNavigationCapability
    nav_cap = MockNavigationCapability(location_service)

    # 构造 navigate_to 任务
    task = Task(
        task_id="test-nav-001",
        intent="navigate_to",
        params={"target": name},
    )

    # 执行并验证
    result = asyncio.get_event_loop().run_until_complete(nav_cap.execute(task))

    # 验证成功
    assert result.success is True, f"导航到 '{name}' 应成功，但返回: {result.message}"
    # 验证 message 包含地名
    assert name in result.message, (
        f"成功结果的 message 应包含地名 '{name}'，但实际为: '{result.message}'"
    )
