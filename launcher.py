import os
import sys
import time
import subprocess
import httpx
from pathlib import Path
from config import GITHUB_TOKEN

REPO = "C00p1r/llm-local-bridge"
BRANCH = "main"
POLL_INTERVAL = 60  # 每 60 秒檢查一次 GitHub 遠端更新
BASE_DIR = Path(__file__).resolve().parent

def get_remote_head_sha() -> str | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    
    url = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
    try:
        res = httpx.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json().get("sha")
    except Exception as e:
        print(f"[Watcher] 檢查遠端更新失敗: {e}")
    return None

def get_local_head_sha() -> str | None:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=True
        )
        return res.stdout.strip()
    except Exception:
        return None

def update_repo() -> bool:
    print("[Watcher] 偵測到遠端新版本，執行強制拉取並對齊遠端 (fetch + reset --hard)...")
    fetch_res = subprocess.run(["git", "fetch", "origin", BRANCH], cwd=str(BASE_DIR))
    if fetch_res.returncode != 0:
        print("[Watcher] git fetch 失敗")
        return False
    
    reset_res = subprocess.run(["git", "reset", "--hard", f"origin/{BRANCH}"], cwd=str(BASE_DIR))
    return reset_res.returncode == 0

def run_guardian():
    server_process = None
    
    def start_server():
        nonlocal server_process
        print("[Watcher] 啟動 server.py...")
        server_process = subprocess.Popen([sys.executable, "server.py"], cwd=str(BASE_DIR))

    start_server()

    try:
        while True:
            time.sleep(POLL_INTERVAL)
            local_sha = get_local_head_sha()
            remote_sha = get_remote_head_sha()

            if remote_sha and local_sha and remote_sha != local_sha:
                print(f"[Watcher] 發現新 Commit: {remote_sha[:7]} (本地: {local_sha[:7]})")
                
                if server_process:
                    print("[Watcher] 停止現有伺服器...")
                    server_process.terminate()
                    try:
                        server_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server_process.kill()

                if update_repo():
                    print("[Watcher] 更新成功，正在重啟服務端...")
                else:
                    print("[Watcher] 更新失敗，嘗試使用現有代碼重啟...")
                
                start_server()
    except KeyboardInterrupt:
        print("
[Watcher] 收到中斷訊號，正在關閉伺服器...")
        if server_process:
            server_process.terminate()
            server_process.wait()

if __name__ == "__main__":
    run_guardian()
