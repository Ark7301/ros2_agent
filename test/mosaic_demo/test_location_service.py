"""
LocationService 属性测试

Property 10: LocationService 添加-查询 round-trip
**Validates: Requirements 8.2, 8.4**

Property 11: LocationService 未注册地名返回 None
**Validates: Requirements 8.3**

使用 hypothesis 库验证 LocationService 的核心行为。
"""

import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from mosaic_demo.capabilities.location_service import LocationService


# ---- 自定义 Hypothesis Strategy ----

# 地名策略：非空字符串
location_name = st.text(min_size=1, max_size=30)

# 坐标策略：包含 x、y、theta 三个 float 字段
coords_strategy = st.fixed_dictionaries({
    "x": st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    "y": st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    "theta": st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
})


# ---- 属性测试 ----


class TestLocationServiceAddQueryRoundTrip:
    """Property 10: LocationService 添加-查询 round-trip

    **Validates: Requirements 8.2, 8.4**
    """

    @given(name=location_name, coords=coords_strategy)
    @settings(max_examples=100)
    def test_add_then_resolve_returns_same_coords(self, name: str, coords: dict):
        """
        对于任意地名字符串和坐标字典（包含 x、y、theta），
        添加到 LocationService 后查询该地名应返回相同的坐标。
        """
        service = LocationService()
        service.add_location(name, coords)

        result = service.resolve_location(name)

        assert result is not None
        assert result["x"] == coords["x"]
        assert result["y"] == coords["y"]
        assert result["theta"] == coords["theta"]

    @given(
        names_and_coords=st.lists(
            st.tuples(location_name, coords_strategy),
            min_size=1,
            max_size=10,
            unique_by=lambda t: t[0],
        )
    )
    @settings(max_examples=50)
    def test_multiple_add_then_resolve_all(self, names_and_coords):
        """
        添加多个地名后，每个地名都应能正确查询到对应坐标。
        """
        service = LocationService()

        for name, coords in names_and_coords:
            service.add_location(name, coords)

        for name, coords in names_and_coords:
            result = service.resolve_location(name)
            assert result is not None
            assert result["x"] == coords["x"]
            assert result["y"] == coords["y"]
            assert result["theta"] == coords["theta"]


class TestLocationServiceUnregisteredReturnsNone:
    """Property 11: LocationService 未注册地名返回 None

    **Validates: Requirements 8.3**
    """

    @given(name=location_name)
    @settings(max_examples=100)
    def test_resolve_unregistered_name_returns_none(self, name: str):
        """
        对于任意不在 LocationService 中的地名字符串，查询应返回 None。
        """
        service = LocationService()

        result = service.resolve_location(name)

        assert result is None

    @given(
        registered_name=location_name,
        unregistered_name=location_name,
        coords=coords_strategy,
    )
    @settings(max_examples=100)
    def test_resolve_different_name_returns_none(
        self, registered_name: str, unregistered_name: str, coords: dict
    ):
        """
        注册一个地名后，查询不同的地名应返回 None。
        """
        # 确保两个地名不同
        assume(registered_name != unregistered_name)

        service = LocationService()
        service.add_location(registered_name, coords)

        result = service.resolve_location(unregistered_name)

        assert result is None
