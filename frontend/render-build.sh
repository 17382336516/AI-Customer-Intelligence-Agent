#!/usr/bin/env sh
# Render 前端构建脚本：安装依赖并注入后端地址后打包静态文件。
# VITE_API_BASE_URL 来自 Render 环境变量（连到后端 Web Service 的域名）。
set -e

echo "VITE_API_BASE_URL=${VITE_API_BASE_URL:-<未设置，将相对路径访问>}"

corepack enable
pnpm install --frozen-lockfile
pnpm run build
