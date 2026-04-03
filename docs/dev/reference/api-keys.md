- title: API Keys Reference
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, dev, reference, api

# MiniMax API 配置

## API Key

```
sk-api-iX71Adv4hJbXZigv29nYEYuI9_hVKCPgGDI7aj0q2x7zXnctmG1q2KdYqhfw7ifjKPnsuFCiY7vuQFzzLKAxHWWu0tnpwe8RdqsdEXnBgmDp9yYvf61XSeE
```

## 接入信息

- API Base URL: `https://api.minimaxi.com/anthropic`
- 兼容协议: Anthropic API 格式
- 环境变量名: `MINIMAX_API_KEY`

## 支持的模型

| 模型名称 | 上下文窗口 | 说明 |
|---------|-----------|------|
| MiniMax-M2.5 | 204,800 | 顶尖性能与极致性价比（~60 TPS） |
| MiniMax-M2.5-highspeed | 204,800 | M2.5 极速版（~100 TPS） |
| MiniMax-M2.1 | 204,800 | 强大多语言编程能力（~60 TPS） |
| MiniMax-M2.1-highspeed | 204,800 | M2.1 极速版（~100 TPS） |
| MiniMax-M2 | 204,800 | 专为高效编码与 Agent 工作流而生 |

## 参考文档

- Anthropic API 兼容格式文档: https://platform.minimaxi.com/docs/api-reference/text-anthropic-api

## 注意事项

- 多轮 Function Call 对话中，必须将完整的 `response.content`（包含 thinking/text/tool_use 等所有块）回传到对话历史
- temperature 取值范围 (0.0, 1.0]，建议取值 1
- 支持 thinking（推理链）、tool_use、流式响应
- 不支持图像和文档输入
