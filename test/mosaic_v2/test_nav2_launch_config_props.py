# test/mosaic_v2/test_nav2_launch_config_props.py
"""Nav2LaunchConfig 属性测试 — 使用 hypothesis 验证 Nav2 参数有效性"""

from __future__ import annotations

import os
import tempfile

import yaml
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from mosaic.runtime.nav2_launch_config import Nav2SimParams, Nav2LaunchConfig


class TestNav2ParamsValidity:
    """Property 6: Nav2 参数有效性

    ∀ generated_params:
      use_sim_time = True ∧ inflation_radius > robot_radius ∧ max_particles > min_particles

    使用 hypothesis 生成随机有效的 Nav2SimParams，生成参数文件后解析回来验证属性成立。

    **Validates: Requirements 3.1, 3.2**
    """

    @given(
        robot_radius=st.floats(min_value=0.01, max_value=1.0),
        inflation_extra=st.floats(min_value=0.01, max_value=1.0),
        min_particles=st.integers(min_value=100, max_value=1000),
        particle_extra=st.integers(min_value=1, max_value=5000),
        max_vel_x=st.floats(min_value=0.01, max_value=5.0),
        max_vel_theta=st.floats(min_value=0.01, max_value=5.0),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_nav2_params_validity(
        self,
        robot_radius: float,
        inflation_extra: float,
        min_particles: int,
        particle_extra: int,
        max_vel_x: float,
        max_vel_theta: float,
    ) -> None:
        """生成的参数文件中 use_sim_time=True、inflation_radius > robot_radius、max_particles > min_particles"""
        # 构造满足约束的有效参数
        params = Nav2SimParams(
            robot_radius=robot_radius,
            inflation_radius=robot_radius + inflation_extra,
            amcl_min_particles=min_particles,
            amcl_max_particles=min_particles + particle_extra,
            max_vel_x=max_vel_x,
            max_vel_theta=max_vel_theta,
        )
        config = Nav2LaunchConfig(mosaic_config={})
        config._nav2_params = params

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nav2_params.yaml")
            config.generate_nav2_params(path)

            with open(path) as f:
                data = yaml.safe_load(f)

            # 验证所有配置段的 use_sim_time 为 True
            assert data["amcl"]["ros__parameters"]["use_sim_time"] is True
            assert data["controller_server"]["ros__parameters"]["use_sim_time"] is True
            assert data["planner_server"]["ros__parameters"]["use_sim_time"] is True

            # 验证 inflation_radius > robot_radius（local_costmap）
            local_cm = data["local_costmap"]["local_costmap"]["ros__parameters"]
            assert local_cm["inflation_layer"]["inflation_radius"] > local_cm["robot_radius"]

            # 验证 max_particles > min_particles
            amcl = data["amcl"]["ros__parameters"]
            assert amcl["max_particles"] > amcl["min_particles"]
