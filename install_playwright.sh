#!/bin/bash

set -e

echo "========================================="
echo " Playwright 环境一键安装脚本"
echo " Alibaba Cloud Linux 3"
echo "========================================="

# 检查权限
if [ "$EUID" -ne 0 ]; then
    echo "请使用 root 用户运行"
    exit 1
fi

echo
echo "[1/4] 安装 Playwright 运行依赖..."

dnf install -y \
    atk \
    at-spi2-atk \
    gtk3 \
    libXcomposite \
    libXcursor \
    libXdamage \
    libXext \
    libXi \
    libXrandr \
    libXScrnSaver \
    libXtst \
    pango \
    alsa-lib \
    mesa-libgbm \
    nss \
    nspr \
    cups-libs \
    libdrm \
    libxkbcommon

echo
echo "[2/4] 检查 Python..."

if ! command -v python3 >/dev/null 2>&1; then
    echo "未发现 python3"
    exit 1
fi

python3 --version

echo
echo "[3/4] 安装 Playwright..."

python3 -m pip install -U pip
python3 -m pip install -U playwright

echo
echo "[4/4] 下载 Chromium..."

python3 -m playwright install chromium

echo
echo "开始验证浏览器启动..."

python3 << 'EOF'
from playwright.sync_api import sync_playwright

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )
        page = browser.new_page()
        page.goto("https://www.baidu.com", timeout=30000)
        print("Playwright OK")
        print("页面标题:", page.title())
        browser.close()
except Exception as e:
    print("启动失败:")
    print(e)
    raise
EOF

echo
echo "========================================="
echo " Playwright 安装完成"
echo "========================================="