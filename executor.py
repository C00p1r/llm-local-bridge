import asyncio
from pathlib import Path
from config import WORKSPACE_DIR, MAX_OUTPUT_CHARS, DEFAULT_TIMEOUT_SEC

# 容器映像檔（可換成包含 python/node 的環境，如 python:3.11-slim 或 alpine）
DOCKER_IMAGE = "python:3.11-slim"

async def run_shell_command(command: str, timeout: int = DEFAULT_TIMEOUT_SEC) -> dict:
    # 確保工作目錄存在且為絕對路徑
    workspace_abs = str(Path(WORKSPACE_DIR).resolve())

    # 組裝 Docker 沙盒指令
    docker_args = [
        "docker", "run",
        "--rm",                          # 執行完畢即銷毀容器
        "--network", "none",             # 完全禁用容器網路（防外洩）
        "--cpus", "2.0",                 # 限制 CPU 核心數
        "--memory", "1g",                # 限制記憶體 1GB
        "-v", f"{workspace_abs}:/workspace:rw",  # 僅掛載工作區
        "-w", "/workspace",              # 工作目錄鎖定在 /workspace
        DOCKER_IMAGE,
        "sh", "-c", command
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *docker_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {
                "status": "timeout", 
                "output": f"指令執行逾時 ({timeout}s)", 
                "exit_code": -1
            }

        out_decoded = stdout.decode("utf-8", errors="replace")
        err_decoded = stderr.decode("utf-8", errors="replace")
        combined = out_decoded + (f"\n[STDERR]\n{err_decoded}" if err_decoded else "")

        if len(combined) > MAX_OUTPUT_CHARS:
            combined = combined[:MAX_OUTPUT_CHARS] + "\n\n[Warning: Output truncated...]"

        return {
            "status": "success" if process.returncode == 0 else "failed",
            "output": combined.strip() or "[Empty Output]",
            "exit_code": process.returncode
        }

    except FileNotFoundError:
        return {
            "status": "error", 
            "output": "未在系統中找到 Docker，請確認 Docker Desktop / Daemon 是否已啟動並加入 PATH。", 
            "exit_code": -1
        }
    except Exception as e:
        return {"status": "error", "output": str(e), "exit_code": -1}
def write_workspace_file(path: str, content: str) -> dict:
    try:
        target_path = (Path(WORKSPACE_DIR) / path).resolve()
        workspace_path = Path(WORKSPACE_DIR).resolve()
        if not str(target_path).startswith(str(workspace_path)):
            return {"status": "error", "output": "[Bridge] Path out of workspace", "exit_code": -1}
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding='utf-8')
        return {"status": "success", "output": f"File {path} written successfully", "exit_code": 0}
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] Failed to write file: {str(e)}", "exit_code": -1}
