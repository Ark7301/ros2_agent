# mosaic/runtime/scene_analyzer.py
"""VLM 语义分析器 — 调用视觉语言模型分析 RGB 图像

核心功能：
1. 调用 VLM API（GPT-4V / 开源 VLM）分析 RGB 图像
2. 解析 VLM 返回的 JSON 格式识别结果
3. 像素坐标到世界坐标转换（相机内参 + SLAM TF 变换）
4. 错误处理：API 失败/超时记录日志并跳过，JSON 不合法记录警告并丢弃
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── 数据结构 ──

@dataclass
class DetectedObject:
    """VLM 识别的物体"""
    label: str
    category: str  # object / furniture / appliance
    bbox_pixels: tuple[int, int, int, int]  # (x1, y1, x2, y2)
    world_position: tuple[float, float] | None = None
    relations: list[dict] = field(default_factory=list)


# ── VLM 语义分析器 ──

class SceneAnalyzer:
    """VLM 语义分析器 — 调用 VLM API 分析图像帧

    支持 GPT-4V 和开源 VLM 两种后端，通过配置切换。
    VLM prompt 包含当前场景图摘要文本（增量识别）。
    """

    # VLM 结构化 prompt 模板
    _PROMPT_TEMPLATE = (
        "请分析这张室内 RGB 图像，识别所有可见物体。\n"
        "返回严格 JSON 格式：\n"
        '{{"objects": [{{"label": "物体名称", "category": "object|furniture|appliance", '
        '"bbox": [x1, y1, x2, y2], "relations": [{{"type": "on_top|inside|next_to", '
        '"target": "目标物体名称"}}]}}]}}\n'
        "注意：\n"
        "- category 只能是 object、furniture、appliance 之一\n"
        "- bbox 为像素坐标 [左上x, 左上y, 右下x, 右下y]\n"
        "- 只返回 JSON，不要其他文字\n"
    )

    _VALID_CATEGORIES = {"object", "furniture", "appliance"}

    def __init__(
        self,
        backend: str = "gpt-4v",
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        timeout_s: float = 30.0,
        camera_intrinsics: dict[str, float] | None = None,
    ) -> None:
        self._backend = backend
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        # 相机内参（用于像素→世界坐标转换）
        self._intrinsics = camera_intrinsics or {
            "fx": 554.0, "fy": 554.0, "cx": 320.0, "cy": 240.0,
            "camera_height": 1.0,
        }

    async def analyze_frame(
        self,
        frame: Any,  # CameraFrame
        scene_context: str = "",
    ) -> list[DetectedObject]:
        """调用 VLM API 分析图像帧，返回检测到的物体列表

        失败时记录日志并返回空列表（不抛异常）。
        """
        try:
            # 构建 prompt（包含场景图摘要用于增量识别）
            prompt = self._build_prompt(scene_context)

            # 调用 VLM API
            raw_response = await self._call_vlm_api(frame.image_data, prompt)

            # 解析 JSON 响应
            detections = self._parse_response(raw_response)

            # 像素坐标到世界坐标转换
            for det in detections:
                det.world_position = self._pixel_to_world(
                    det.bbox_pixels, frame.robot_pose,
                )

            return detections

        except Exception as e:
            # 捕获所有异常（包括 httpx.TimeoutException、httpx.HTTPError）
            err_type = type(e).__name__
            if "Timeout" in err_type:
                logger.error("VLM API 调用超时（backend=%s）", self._backend)
            elif "HTTP" in err_type:
                logger.error("VLM API 调用失败（backend=%s）: %s", self._backend, e)
            else:
                logger.error("VLM 分析异常: %s", e)
            return []

    def _build_prompt(self, scene_context: str) -> str:
        """构建 VLM prompt，包含场景图摘要用于增量识别"""
        prompt = self._PROMPT_TEMPLATE
        if scene_context:
            prompt += (
                f"\n当前已知场景信息（请避免重复标注已知物体，"
                f"关注新出现的物体）：\n{scene_context}\n"
            )
        return prompt

    async def _call_vlm_api(
        self, image_data: bytes, prompt: str,
    ) -> str:
        """调用 VLM API，返回原始响应文本"""
        image_b64 = base64.b64encode(image_data).decode("utf-8")

        if self._backend == "gpt-4v":
            return await self._call_gpt4v(image_b64, prompt)
        else:
            return await self._call_open_vlm(image_b64, prompt)

    async def _call_gpt4v(
        self, image_b64: str, prompt: str,
    ) -> str:
        """调用 GPT-4V API"""
        import httpx

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def _call_open_vlm(
        self, image_b64: str, prompt: str,
    ) -> str:
        """调用开源 VLM API（兼容 OpenAI 格式）"""
        import httpx

        url = f"{self._base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self._backend,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_response(self, raw: str) -> list[DetectedObject]:
        """解析 VLM 返回的 JSON 响应

        JSON 格式不合法时记录警告并返回空列表。
        """
        try:
            # 尝试提取 JSON 块（VLM 可能返回 markdown 代码块）
            json_str = raw.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            data = json.loads(json_str)
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning("VLM 返回的 JSON 格式不合法，丢弃本帧结果: %s", e)
            return []

        objects = data.get("objects", [])
        if not isinstance(objects, list):
            logger.warning("VLM 返回的 objects 字段不是列表，丢弃本帧结果")
            return []

        detections: list[DetectedObject] = []
        for obj in objects:
            try:
                label = str(obj.get("label", ""))
                category = str(obj.get("category", "object"))
                if category not in self._VALID_CATEGORIES:
                    category = "object"
                bbox = obj.get("bbox", [0, 0, 0, 0])
                if not isinstance(bbox, list) or len(bbox) != 4:
                    continue
                relations = obj.get("relations", [])
                if not isinstance(relations, list):
                    relations = []

                detections.append(DetectedObject(
                    label=label,
                    category=category,
                    bbox_pixels=(int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])),
                    relations=relations,
                ))
            except (ValueError, TypeError) as e:
                logger.warning("解析单个物体失败，跳过: %s", e)
                continue

        return detections

    def _pixel_to_world(
        self,
        bbox: tuple[int, int, int, int],
        robot_pose: tuple[float, float, float],
    ) -> tuple[float, float]:
        """像素坐标到世界坐标转换

        简化模型：利用相机内参将 bbox 中心投影到地面平面，
        再通过机器人位姿变换到世界坐标系。
        """
        import math

        # bbox 中心像素坐标
        cx_pixel = (bbox[0] + bbox[2]) / 2.0
        cy_pixel = (bbox[1] + bbox[3]) / 2.0

        # 相机内参
        fx = self._intrinsics["fx"]
        fy = self._intrinsics["fy"]
        cx = self._intrinsics["cx"]
        cy = self._intrinsics["cy"]
        cam_h = self._intrinsics["camera_height"]

        # 像素 → 相机坐标系（假设物体在地面平面 z=0）
        # 投影到地面：depth = camera_height / ((cy_pixel - cy) / fy)
        dy_pixel = cy_pixel - cy
        if abs(dy_pixel) < 1.0:
            dy_pixel = 1.0  # 避免除零
        depth = cam_h * fy / dy_pixel
        depth = max(0.1, min(depth, 10.0))  # 限制合理范围

        # 相机坐标系中的 x 偏移
        x_cam = (cx_pixel - cx) * depth / fx

        # 机器人位姿 → 世界坐标
        rx, ry, theta = robot_pose
        # 相机坐标系：前方为 z 轴（depth），右方为 x 轴
        wx = rx + depth * math.cos(theta) - x_cam * math.sin(theta)
        wy = ry + depth * math.sin(theta) + x_cam * math.cos(theta)

        return (round(wx, 3), round(wy, 3))
