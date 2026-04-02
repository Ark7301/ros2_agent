# mosaic/runtime/vlm_pipeline/vlm_analyzer.py
"""VLM 视觉分析器 — 调用视觉语言模型分析 RGB-D 图像

基于 SceneAnalyzer 的 API 调用模式，增强返回 DetectionResult（含房间分类）。

核心功能：
1. 调用 VLM API（GPT-4V / 兼容 OpenAI 格式的 VLM）分析 RGB 图像
2. 解析 VLM 返回的 JSON 格式识别结果（物体列表 + 房间分类）
3. 错误处理：API 失败/超时记录日志并返回空结果，JSON 不合法记录警告并丢弃
"""

from __future__ import annotations

import base64
import json
import logging

import httpx

from mosaic.runtime.vlm_pipeline.models import (
    CameraFrame,
    DetectedObject,
    DetectionResult,
    RoomClassification,
)

logger = logging.getLogger(__name__)

# 合法的物体类别
_VALID_CATEGORIES = frozenset({"object", "furniture", "appliance"})

# VLM 结构化 prompt 模板
_PROMPT_TEMPLATE = (
    "请分析这张室内 RGB 图像，识别所有可见物体并判断房间类型。\n"
    "返回严格 JSON 格式：\n"
    '{{"objects": [{{"label": "物体名称", "category": "object|furniture|appliance", '
    '"bbox": [x1, y1, x2, y2]}}], '
    '"room_type": "房间类型", "room_confidence": 0.9}}\n'
    "注意：\n"
    "- category 只能是 object、furniture、appliance 之一\n"
    "- bbox 为像素坐标 [左上x, 左上y, 右下x, 右下y]\n"
    "- room_type 为中文房间名称（如 厨房、卧室、客厅）\n"
    "- room_confidence 为 0-1 之间的置信度\n"
    "- 只返回 JSON，不要其他文字\n"
)


class VLMAnalyzer:
    """VLM 视觉分析器 — 调用 VLM API 分析图像帧

    支持 GPT-4V 和兼容 OpenAI 格式的 VLM 后端，通过 backend 参数切换。
    """

    def __init__(
        self,
        backend: str = "gpt-4v",
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        timeout_s: float = 30.0,
    ) -> None:
        self._backend = backend
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    async def analyze_frame(
        self,
        frame: CameraFrame,
        scene_context: str = "",
    ) -> DetectionResult:
        """分析单帧，返回物体列表 + 房间分类

        失败时返回空 DetectionResult，不抛异常。
        """
        try:
            prompt = self._build_prompt(scene_context)
            raw_response = await self._call_vlm_api(frame.image_data, prompt)
            return self._parse_response(raw_response)
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            logger.error("VLM API 调用失败（backend=%s）: %s", self._backend, e)
            return DetectionResult()
        except httpx.HTTPError as e:
            logger.error("VLM API HTTP 错误（backend=%s）: %s", self._backend, e)
            return DetectionResult()
        except Exception as e:
            logger.error("VLM 分析异常: %s", e)
            return DetectionResult()

    def _build_prompt(self, scene_context: str) -> str:
        """构建 VLM prompt，包含场景图摘要用于增量识别

        纯函数，方便属性测试直接调用。
        """
        prompt = _PROMPT_TEMPLATE
        if scene_context:
            prompt += (
                f"\n当前已知场景信息（请避免重复标注已知物体，"
                f"关注新出现的物体）：\n{scene_context}\n"
            )
        return prompt

    def _parse_response(self, raw: str) -> DetectionResult:
        """解析 VLM JSON 响应，返回 DetectionResult

        支持 markdown 代码块提取。JSON 不合法时记录警告并返回空结果。
        纯函数，方便属性测试直接调用。
        """
        try:
            json_str = self._extract_json(raw)
            data = json.loads(json_str)
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning("VLM 返回的 JSON 格式不合法，丢弃本帧结果: %s", e)
            return DetectionResult()

        # JSON 顶层必须是 dict
        if not isinstance(data, dict):
            logger.warning("VLM 返回的 JSON 顶层不是对象，丢弃本帧结果")
            return DetectionResult()

        # 解析物体列表
        objects = self._parse_objects(data)

        # 解析房间分类
        room_classification = self._parse_room(data)

        return DetectionResult(
            objects=objects,
            room_classification=room_classification,
        )

    # ── 内部辅助方法 ──

    @staticmethod
    def _extract_json(raw: str) -> str:
        """从原始响应中提取 JSON 字符串，支持 markdown 代码块"""
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return text

    @staticmethod
    def _parse_objects(data: dict) -> list[DetectedObject]:
        """从解析后的 JSON 字典中提取物体列表"""
        raw_objects = data.get("objects", [])
        if not isinstance(raw_objects, list):
            logger.warning("VLM 返回的 objects 字段不是列表，丢弃物体结果")
            return []

        detections: list[DetectedObject] = []
        for obj in raw_objects:
            if not isinstance(obj, dict):
                continue
            try:
                label = str(obj.get("label", ""))
                if not label:
                    continue

                category = str(obj.get("category", "object"))
                if category not in _VALID_CATEGORIES:
                    category = "object"

                bbox = obj.get("bbox", [0, 0, 0, 0])
                if not isinstance(bbox, list) or len(bbox) != 4:
                    continue

                # 确保 bbox 值为整数
                bbox_ints = (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))

                detections.append(DetectedObject(
                    label=label,
                    category=category,
                    bbox_pixels=bbox_ints,
                ))
            except (ValueError, TypeError) as e:
                logger.warning("解析单个物体失败，跳过: %s", e)
                continue

        return detections

    @staticmethod
    def _parse_room(data: dict) -> RoomClassification | None:
        """从解析后的 JSON 字典中提取房间分类"""
        room_type = data.get("room_type")
        if not room_type or not isinstance(room_type, str):
            return None

        try:
            confidence = float(data.get("room_confidence", 0.0))
            # 限制置信度范围
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.0

        return RoomClassification(room_type=room_type, confidence=confidence)

    async def _call_vlm_api(self, image_data: bytes, prompt: str) -> str:
        """调用 VLM API，返回原始响应文本"""
        image_b64 = base64.b64encode(image_data).decode("utf-8")

        url = f"{self._base_url}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # GPT-4V 和兼容 OpenAI 格式的 VLM 使用相同的请求结构
        model = "gpt-4-vision-preview" if self._backend == "gpt-4v" else self._backend
        payload = {
            "model": model,
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
                },
            ],
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
