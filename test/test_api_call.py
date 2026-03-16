"""
美的 AIMP Claude API 调用测试脚本

测试非流式接口连通性，验证 v3 接口地址是否正常工作。
"""

import httpx
import json
import sys
import time

# ===== 配置 =====
API_KEY = "msk-bf1551c225113628c953505667cf5328b323e21fa79411578625843e1f123c02"
MODEL_ID = "anthropic.claude-sonnet-4-5-20250929-v1:0"
AIGC_USER = "ex_dengyj5"

SYNC_URL = "https://aimpapi.midea.com/t-aigc/mip-chat-app/claude/official/standard/sync/v3/chat/completions"
STREAM_URL = "https://aimpapi.midea.com/t-aigc/mip-chat-app/claude/official/standard/stream/v3/chat/completions"

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": API_KEY,
    "Aimp-Biz-Id": MODEL_ID,
    "AIGC-USER": AIGC_USER,
}

# 简单测试 payload
PAYLOAD = {
    "modelId": MODEL_ID,
    "messages": [
        {
            "role": "user",
            "content": [{"text": "你好，请用一句话介绍你自己"}],
        }
    ],
    "inferenceConfig": {
        "maxTokens": 256,
        "temperature": 0.1,
    },
}


def test_sync():
    """测试非流式接口"""
    print("=" * 50)
    print("测试非流式接口 (sync)")
    print(f"URL: {SYNC_URL}")
    print("=" * 50)

    start = time.time()
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(SYNC_URL, json=PAYLOAD, headers=HEADERS)
            elapsed = time.time() - start

            print(f"状态码: {resp.status_code}")
            print(f"耗时: {elapsed:.2f}s")

            if resp.status_code == 200:
                data = resp.json()
                print(f"stopReason: {data.get('stopReason')}")

                # 提取回复文本
                msg = data.get("output", {}).get("message", {})
                contents = msg.get("content", [])
                for c in contents:
                    if "text" in c:
                        print(f"回复: {c['text']}")

                # token 用量
                usage = data.get("usage", {})
                if usage:
                    print(f"token 用量: input={usage.get('inputTokens')}, output={usage.get('outputTokens')}, total={usage.get('totalTokens')}")

                print("\n✅ 非流式接口测试通过")
            else:
                print(f"响应体: {resp.text[:500]}")
                print("\n❌ 非流式接口测试失败")

    except Exception as e:
        print(f"❌ 请求异常: {e}")


def test_stream():
    """测试流式接口"""
    print("\n" + "=" * 50)
    print("测试流式接口 (stream)")
    print(f"URL: {STREAM_URL}")
    print("=" * 50)

    start = time.time()
    try:
        with httpx.Client(timeout=60) as client:
            with client.stream("POST", STREAM_URL, json=PAYLOAD, headers=HEADERS) as resp:
                elapsed_first = None
                print(f"状态码: {resp.status_code}")

                if resp.status_code == 200:
                    chunk_count = 0
                    for chunk in resp.iter_text():
                        if elapsed_first is None:
                            elapsed_first = time.time() - start
                        chunk_count += 1
                        # 只打印前几个 chunk 作为示例
                        if chunk_count <= 3:
                            preview = chunk[:200].replace("\n", "\\n")
                            print(f"  chunk[{chunk_count}]: {preview}...")

                    elapsed = time.time() - start
                    print(f"首 chunk 耗时: {elapsed_first:.2f}s")
                    print(f"总耗时: {elapsed:.2f}s")
                    print(f"总 chunk 数: {chunk_count}")
                    print("\n✅ 流式接口测试通过")
                else:
                    # 非 200 时需要先 read 再取 text
                    resp.read()
                    print(f"响应体: {resp.text[:500]}")
                    print("\n❌ 流式接口测试失败")

    except Exception as e:
        print(f"❌ 请求异常: {e}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode in ("sync", "all"):
        test_sync()
    if mode in ("stream", "all"):
        test_stream()
