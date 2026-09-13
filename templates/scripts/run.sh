#!/bin/bash
#==========================================
# 新闻采集系统 - 启动脚本 (Linux/Mac)
# 运行方式: ./run.sh [--debug] [--host 地址] [--port 端口]
#==========================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 解析参数
HOST="0.0.0.0"
PORT=5000
DEBUG=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --debug)
            DEBUG=true
            shift
            ;;
        --help)
            echo -e "${CYAN}========================================${NC}"
            echo -e "${CYAN}  新闻数据采集系统 - 启动参数${NC}"
            echo -e "${CYAN}========================================${NC}"
            echo ""
            echo -e "${WHITE}用法: ./run.sh [选项]${NC}"
            echo ""
            echo -e "${WHITE}选项:${NC}"
            echo -e "  --host <地址>  绑定地址 (默认: 0.0.0.0)"
            echo -e "  --port <端口>  端口号 (默认: 5000)"
            echo -e "  --debug        调试模式"
            echo -e "  --help         显示此帮助信息"
            echo ""
            echo -e "${WHITE}示例:${NC}"
            echo -e "  ./run.sh                    # 默认启动"
            echo -e "  ./run.sh --debug            # 调试模式"
            echo -e "  ./run.sh --port 8080        # 指定端口"
            echo -e "  ./run.sh --host 127.0.0.1   # 本地访问"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  新闻数据采集系统 - Web 管理平台${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# 检查虚拟环境
VENV_PATH="$SCRIPT_DIR/.venv"
PYTHON_PATH="$VENV_PATH/bin/python"

if [ ! -f "$PYTHON_PATH" ]; then
    echo -e "${RED}✗ 虚拟环境未找到!${NC}"
    echo ""
    echo -e "${YELLOW}请先运行 setup_venv.sh 创建虚拟环境:${NC}"
    echo -e "${GRAY}  ./scripts/setup_venv.sh${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 虚拟环境已找到${NC}"
echo ""

# 构建启动命令
APP_PATH="$SCRIPT_DIR/app.py"

if [ "$DEBUG" = true ]; then
    echo -e "${YELLOW}调试模式: 启用${NC}"
    "$PYTHON_PATH" "$APP_PATH" --host "$HOST" --port "$PORT" --debug
else
    echo -e "${GRAY}调试模式: 禁用${NC}"
    "$PYTHON_PATH" "$APP_PATH" --host "$HOST" --port "$PORT"
fi
