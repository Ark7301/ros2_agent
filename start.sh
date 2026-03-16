#!/bin/bash
# MOSAIC Demo 一键启动脚本

# 切换到脚本所在目录（项目根目录）
cd "$(dirname "$0")"

# 设置 API Key（MiniMax Anthropic API）
export MINIMAX_API_KEY="sk-api-iX71Adv4hJbXZigv29nYEYuI9_hVKCPgGDI7aj0q2x7zXnctmG1q2KdYqhfw7ifjKPnsuFCiY7vuQFzzLKAxHWWu0tnpwe8RdqsdEXnBgmDp9yYvf61XSeE"

# 如需使用美的 AIMP，取消下面注释并在 agent_config.yaml 中将 type 改为 midea_claude
# export MIDEA_API_KEY="your_midea_api_key_here"

# 启动
python3 -m mosaic_demo.main
