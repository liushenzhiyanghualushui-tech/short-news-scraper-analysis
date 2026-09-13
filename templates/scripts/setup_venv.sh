#!/bin/bash
#==========================================
# 新闻采集系统 - 虚拟环境设置脚本 (Linux/Mac)
# 运行方式: ./setup_venv.sh
#==========================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  新闻数据采集系统 - 虚拟环境设置${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# 检查 Python 是否安装
echo -e "${YELLOW}[1/4] 检查 Python 环境...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    echo -e "${GREEN}  ✓ Python 已安装: $PYTHON_VERSION${NC}"
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_VERSION=$(python --version 2>&1)
    echo -e "${GREEN}  ✓ Python 已安装: $PYTHON_VERSION${NC}"
    PYTHON_CMD="python"
else
    echo -e "${RED}  ✗ Python 未找到，请先安装 Python 3.8+${NC}"
    echo -e "${YELLOW}    下载地址: https://www.python.org/downloads/${NC}"
    exit 1
fi

# 创建虚拟环境
echo ""
echo -e "${YELLOW}[2/4] 创建虚拟环境...${NC}"
VENV_PATH="$SCRIPT_DIR/.venv"

if [ -d "$VENV_PATH" ]; then
    echo -e "${YELLOW}  ⚠  虚拟环境已存在，是否重新创建? [y/N]${NC}"
    read -r choice
    if [ "$choice" = "y" ] || [ "$choice" = "Y" ]; then
        echo -e "${YELLOW}  正在删除现有虚拟环境...${NC}"
        rm -rf "$VENV_PATH"
    else
        echo -e "${GRAY}  跳过虚拟环境创建${NC}"
    fi
fi

if [ ! -d "$VENV_PATH" ]; then
    $PYTHON_CMD -m venv .venv
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}  ✓ 虚拟环境创建成功${NC}"
    else
        echo -e "${RED}  ✗ 虚拟环境创建失败${NC}"
        exit 1
    fi
fi

# 激活虚拟环境并安装依赖
echo ""
echo -e "${YELLOW}[3/4] 安装 Python 依赖包...${NC}"

PIP_PATH="$VENV_PATH/bin/pip"

# 升级 pip
"$VENV_PATH/bin/pip" install --upgrade pip --quiet 2>/dev/null || echo -e "${YELLOW}  ⚠ pip 升级失败，继续安装依赖...${NC}"

# 安装 requirements.txt 中的依赖
"$VENV_PATH/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}  ✓ 依赖安装完成${NC}"
else
    echo -e "${RED}  ✗ 依赖安装失败${NC}"
    exit 1
fi

# 完成
echo ""
echo -e "${YELLOW}[4/4] 设置完成!${NC}"
echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  虚拟环境已配置完成!${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${WHITE}启动项目:${NC}"
echo -e "${GRAY}  ./run.sh                    # 启动 Web 服务${NC}"
echo -e "${GRAY}  ./run.sh --debug            # 调试模式启动${NC}"
echo -e "${GRAY}  ./run.sh --host 127.0.0.1   # 指定地址${NC}"
echo ""
echo -e "${WHITE}手动激活虚拟环境:${NC}"
echo -e "${GRAY}  source .venv/bin/activate${NC}"
echo -e "${GRAY}  pip install -r requirements.txt${NC}"
echo -e "${GRAY}  python app.py${NC}"
echo ""
