import uuid
import os
from pathlib import Path
from config import WORKSPACE_DIR, MAX_OUTPUT_CHARS, DEFAULT_TIMEOUT_SEC

DOCKER_IMAGE = "python:3.11-slim"

def _get_docker_user_args() -> list:
    """在 POSIX / WSL 環境自動對齊宿主機 UID:GID，防止產生 root 唯讀檔案鎖死宿主操作"""
    try:
        if hasattr(os, "getuid") and hasattr(os, "getgid"):
            return ["--user", f"{os.getuid()}:{os.getgid()}"]
    except Exception:
        pass
    return []

async def run_shell_command(command: str, timeout: int = DEFAULT_TIMEOUT_SEC) -> dict:
    import asyncio
    workspace_abs = str(Path(WORKSPACE_DIR).resolve())

    docker_args = [
        "docker", "run",
        "--rm",
        "--network", "none",
        "--cpus", "2.0",
        "--memory", "1g",
        *(_get_docker_user_args()),
        "-v", f"{workspace_abs}:/workspace:rw",
        "-w", "/workspace",
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

async def run_transient_script(code: str, language: str = "python", timeout: int = DEFAULT_TIMEOUT_SEC) -> dict:
    lang_clean = language.lower().strip()
    ext_map = {
        "python": (".py", "python"),
        "py": (".py", "python"),
        "bash": (".sh", "bash"),
        "sh": (".sh", "sh"),
        "node": (".js", "node"),
        "javascript": (".js", "node"),
    }
    ext, runner = ext_map.get(lang_clean, (".sh", "sh"))
    workspace_path = Path(WORKSPACE_DIR).resolve()
    temp_filename = f".temp_{uuid.uuid4().hex[:8]}{ext}"
    temp_file_path = workspace_path / temp_filename

    try:
        normalized_code = code.replace("\r\n", "\n").replace("\r", "\n")
        temp_file_path.write_text(normalized_code, encoding="utf-8", newline='\n')
        cmd = f"{runner} {temp_filename}"
        return await run_shell_command(cmd, timeout=timeout)
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] 暫存腳本執行異常: {str(e)}", "exit_code": -1}
    finally:
        try:
            if temp_file_path.exists():
                temp_file_path.unlink()
        except Exception:
            pass
