#!/bin/bash
# MOSAIC v2 Gateway 启动脚本

# 切换到脚本所在目录（项目根目录）
cd "$(dirname "$0")"

# 设置 API Key（MiniMax API）
export MINIMAX_API_KEY="sk-api-CDCMDAwHV75UcLRdpExGx7_vuPFly0XsCGrC6x_vf83iIvjfOgRDTDz5g6tMuFyU9-cCFe_8J2NTvDvxPUAdn5_ELgkritr-wNgpDN8yQIC-w6OFqN6bLy8"

# 启动 MOSAIC v2 Gateway
python3 -c "from mosaic.gateway.server import main; main()"
