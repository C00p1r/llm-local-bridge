# LLM Local Bridge — 沙盒執行映像
# 目的：在維持 --network none 的前提下，提供 node / git / rg 與預裝 Python 模組
# 建置（需在主機端、有網路時執行一次）：
#   docker build -t llm-bridge-sandbox:latest sandbox/

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ── 系統工具層 ────────────────────────────────────────────
# git: 版本控制（沙盒內唯讀用途）
# ripgrep: search_codebase 極速檢索
# nodejs/npm: JS/TS 語法檢查與執行
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        ripgrep \
        curl \
        ca-certificates \
        nodejs \
        npm \
        jq \
        less \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# ── Python 模組層（核心）────────────────────────────────
COPY requirements.sandbox.txt /tmp/requirements.sandbox.txt
RUN pip install -r /tmp/requirements.sandbox.txt

# ── Python 模組層（選用/重量級，預設不裝）─────────────
# 如需完整環境，取消下一行註解後重新建置
# COPY requirements.sandbox-full.txt /tmp/requirements.sandbox-full.txt
# RUN pip install -r /tmp/requirements.sandbox-full.txt

WORKDIR /workspace
CMD ["sh"]
