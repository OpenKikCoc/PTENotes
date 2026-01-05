#!/bin/bash

# 获取脚本所在目录的绝对路径，确保无论在哪里执行脚本，路径都正确
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "正在启动 Python Docker 容器..."
echo "挂载目录: $SCRIPT_DIR"

# 运行 Docker 容器
# --rm: 容器退出后自动删除
# -v "$SCRIPT_DIR":/app: 将本地 vocabulary 目录挂载到容器内的 /app 目录
# -w /app: 设置容器内的工作目录为 /app
# python:3.9-slim: 使用 Python 3.9 精简版镜像
# 命令部分: 先安装依赖 (使用清华源加速)，然后执行脚本
# 去掉 -it 以避免非交互式环境下的 TTY 错误
docker run --rm \
    -v "$SCRIPT_DIR":/app \
    -w /app \
    python:3.9-slim \
    /bin/bash -c "pip install requests beautifulsoup4 -i https://pypi.tuna.tsinghua.edu.cn/simple && python _generate_vocab.py"

echo "执行完成。"

