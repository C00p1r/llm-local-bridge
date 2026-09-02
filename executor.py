import uuid
from pathlib import Path
from config import WORKSPACE_DIR, MAX_OUTPUT_CHARS, DEFAULT_TIMEOUT_SEC

# 容器映像檔（包含常用執行環境）
DOCKER_IMAGE = "python:3.11-slim"

async def run_shell_command(command: str, timeout: int = DEFAULT_TIMEOUT_SEC) -> dict:
    import asyncio
    workspace_abs = str(Path(WORKSPACE_DIR).resolve())

    docker_args = [
        "docker", "run",
        "--rm",
        "--network", "none",
        "--cpus", "2.0",
        "--memory", "1g",
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

async def run_transient_script(code: str, language: str = "python", timeout: int = DEFAULT_TIMEOUT_SEC) -> dict:
    """
    執行暫存腳本：支援 python、bash、sh 等直譯器，沙盒內執行完畢後確保清理。
    """
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
        temp_file_path.write_text(code, encoding="utf-8")
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
