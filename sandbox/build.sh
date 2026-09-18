#!/bin/sh
# 建置沙盒映像（需在有網路的主機端執行一次）
# 用法：sh sandbox/build.sh [image_name]
set -eu

# 若 shell 支援 pipefail 才啟用（bash/ksh/zsh）；dash/sh 會自動略過，
# 避免 "set: pipefail: invalid option name" 錯誤
if (set -o pipefail) 2>/dev/null; then
    set -o pipefail
fi

IMAGE_NAME="${1:-llm-bridge-sandbox:latest}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

command -v docker >/dev/null 2>&1 || { echo "[ERROR] 找不到 docker CLI"; exit 1; }

echo "[Bridge] 開始建置沙盒映像: ${IMAGE_NAME}"
docker build -t "${IMAGE_NAME}" "${SCRIPT_DIR}"

echo "[Bridge] 建置完成。驗證內含工具："
docker run --rm --network none "${IMAGE_NAME}" sh -c 'node --version; git --version; rg --version | head -1; python --version'

echo "[Bridge] 請於 .env 設定 SANDBOX_IMAGE=${IMAGE_NAME}"
