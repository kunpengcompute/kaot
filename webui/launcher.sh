#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

PORT=${1:-8080}
HOST="0.0.0.0"

echo -e "${CYAN}=== KAOT WebUI ===${NC}"
echo ""
echo -e "${BLUE}启动信息:${NC}"
echo "  端口: $PORT"
echo "  绑定地址: $HOST"
echo "  项目目录: $BASE_DIR"
echo ""

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3${NC}"
    echo "请先安装 Python 3"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${YELLOW}Python版本: ${PYTHON_VERSION}${NC}"
echo ""

echo -e "${BLUE}=== 检查依赖 ===${NC}"

if ! python3 -c "import flask" 2>/dev/null; then
    echo -e "${YELLOW}Flask未安装，正在安装...${NC}"
    pip3 install flask -q
    if [ $? -ne 0 ]; then
        echo -e "${RED}Flask安装失败${NC}"
        echo "请手动执行: pip3 install flask"
        exit 1
    fi
    echo -e "${GREEN}Flask安装成功${NC}"
else
    echo -e "${GREEN}Flask已安装${NC}"
fi

if ! python3 -c "import yaml" 2>/dev/null; then
    echo -e "${YELLOW}PyYAML未安装，正在安装...${NC}"
    pip3 install pyyaml -q
    if [ $? -ne 0 ]; then
        echo -e "${RED}PyYAML安装失败${NC}"
        echo "请手动执行: pip3 install pyyaml"
        exit 1
    fi
    echo -e "${GREEN}PyYAML安装成功${NC}"
else
    echo -e "${GREEN}PyYAML已安装${NC}"
fi

echo ""

get_local_ip() {
    local ip=""
    ip=$(hostname -I | awk '{print $1}' 2>/dev/null)
    if [ -z "$ip" ]; then
        ip=$(ip route get 1 | awk '{print $7; exit}' 2>/dev/null)
    fi
    if [ -z "$ip" ]; then
        ip="127.0.0.1"
    fi
    echo "$ip"
}

LOCAL_IP=$(get_local_ip)

if [ ! -d "$BASE_DIR/output" ]; then
    echo -e "${YELLOW}output目录不存在，正在创建...${NC}"
    mkdir -p "$BASE_DIR/output"
fi

echo -e "${GREEN}=== 启动服务 ===${NC}"
echo ""
echo -e "${GREEN}访问地址:${NC}"
echo "  本机: http://127.0.0.1:$PORT"
echo "  远程: http://$LOCAL_IP:$PORT"
echo ""
echo -e "${YELLOW}提示:${NC}"
echo "  - 按 Ctrl+C 停止服务"
echo "  - 执行调优需要root权限"
echo "  - 日志文件位于: $SCRIPT_DIR/logs/"
echo "  - 配置文件位于: $BASE_DIR/output/"
echo ""
echo "========================================"
echo ""

cd "$SCRIPT_DIR"
python3 app.py --port $PORT --host $HOST