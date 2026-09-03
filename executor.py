import uuid
import ast
import os
import stat
import subprocess
import difflib
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

def _ensure_writable(path_obj: Path):
    """嘗試解除 Docker root 產生的唯讀標記或修復權限"""
    try:
        if path_obj.exists():
            current_mode = path_obj.stat().st_mode
            path_obj.chmod(current_mode | stat.S_IWRITE | stat.S_IREAD)
    except Exception:
        pass

def _validate_python_syntax(file_path: str, code_content: str) -> Optional[str]:
    """若為 .py 檔，檢查 Python AST 語法合法性，避免語法錯誤落地"""
    if file_path.endswith(".py"):
        try:
            ast.parse(code_content, filename=file_path)
        except SyntaxError as se:
            return f"[Bridge] Python 語法驗證失敗 (行 {se.lineno}, 列 {se.offset}): {se.msg}"
    return None

def write_workspace_file(path: str, content: str) -> dict:
    try:
        target_path = (Path(WORKSPACE_DIR) / path).resolve()
        workspace_path = Path(WORKSPACE_DIR).resolve()
        if not str(target_path).startswith(str(workspace_path)):
            return {"status": "error", "output": "[Bridge] Path out of workspace", "exit_code": -1}
        
        normalized_content = content.replace("\r\n", "\n").replace("\r", "\n")
        
        # 寫入前語法自檢
        syntax_err = _validate_python_syntax(path, normalized_content)
        if syntax_err:
            return {"status": "error", "output": syntax_err, "exit_code": -1}

        target_path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_writable(target_path)
        target_path.write_text(normalized_content, encoding='utf-8', newline='\n')
        return {"status": "success", "output": f"File {path} written successfully", "exit_code": 0}
    except PermissionError:
        return {"status": "error", "output": f"[Bridge] 檔案權限不足 (PermissionDenied): {path}，可能是 Docker root 鎖定，請檢查權限。", "exit_code": -1}
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] Failed to write file: {str(e)}", "exit_code": -1}

def replace_file_content(path: str, target: str, replacement: str) -> dict:
    """
    局部精確替換檔案內容：
    1. 驗證路徑安全性。
    2. 檢查檔案是否存在。
    3. 嚴格唯一性驗證：target 必須在原檔中剛好出現 1 次。
    4. 換行符統一正規化為 \n。
    5. 若為 Python 檔，內建語法驗證防護 (AST parse)，失敗則不寫入。
    """
    try:
        target_path = (Path(WORKSPACE_DIR) / path).resolve()
        workspace_path = Path(WORKSPACE_DIR).resolve()
        if not str(target_path).startswith(str(workspace_path)):
            return {"status": "error", "output": "[Bridge] Path out of workspace", "exit_code": -1}
        if not target_path.exists() or not target_path.is_file():
            return {"status": "error", "output": f"[Bridge] File not found: {path}", "exit_code": -1}

        raw_file_content = target_path.read_text(encoding='utf-8')
        norm_file = raw_file_content.replace("\r\n", "\n").replace("\r", "\n")
        norm_target = target.replace("\r\n", "\n").replace("\r", "\n")
        norm_replacement = replacement.replace("\r\n", "\n").replace("\r", "\n")

        occurrences = norm_file.count(norm_target)
        if occurrences == 0:
            return {
                "status": "error",
                "output": f"[Bridge] 替換目標不存在 (0 次相符)。請確認 target 與檔案內容完全吻合。",
                "exit_code": -1
            }
        if occurrences > 1:
            return {
                "status": "error",
                "output": f"[Bridge] 替換目標不具唯一性 (出現 {occurrences} 次)。請提供更多上下文以確保精確匹配。",
                "exit_code": -1
            }

        updated_content = norm_file.replace(norm_target, norm_replacement, 1)
        
        # 語法驗證防護：解析失敗立即中斷，原檔保持乾淨
        syntax_err = _validate_python_syntax(path, updated_content)
        if syntax_err:
            return {"status": "error", "output": syntax_err, "exit_code": -1}

        _ensure_writable(target_path)
        target_path.write_text(updated_content, encoding='utf-8', newline='\n')
        return {
            "status": "success",
            "output": f"File {path} updated successfully via replace_content",
            "exit_code": 0
        }
    except PermissionError:
        return {"status": "error", "output": f"[Bridge] 檔案權限不足 (PermissionDenied): {path}，可能是 Docker root 鎖定。", "exit_code": -1}
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] Failed to replace file content: {str(e)}", "exit_code": -1}

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

def read_workspace_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> dict:
    """
    結構化讀取工作區檔案，支援指定行號範圍並附帶行號，杜絕換行轉義與字串比對誤差。
    """
    try:
        target_path = (Path(WORKSPACE_DIR) / path).resolve()
        workspace_path = Path(WORKSPACE_DIR).resolve()
        if not str(target_path).startswith(str(workspace_path)):
            return {"status": "error", "output": "[Bridge] Path out of workspace", "exit_code": -1}
        if not target_path.exists() or not target_path.is_file():
            return {"status": "error", "output": f"[Bridge] File not found: {path}", "exit_code": -1}

        raw_content = target_path.read_text(encoding='utf-8')
        lines = raw_content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        total_lines = len(lines)

        s_idx = max(1, start_line) if start_line is not None else 1
        e_idx = min(total_lines, end_line) if end_line is not None else total_lines

        if s_idx > total_lines:
            return {"status": "error", "output": f"[Bridge] start_line ({s_idx}) 超出檔案總行數 ({total_lines})", "exit_code": -1}
        if s_idx > e_idx:
            return {"status": "error", "output": f"[Bridge] start_line ({s_idx}) 大於 end_line ({e_idx})", "exit_code": -1}

        selected_lines = lines[s_idx - 1:e_idx]
        formatted_output = [f"{i:>4} | {line}" for i, line in enumerate(selected_lines, start=s_idx)]
        raw_selected_text = "\n".join(selected_lines)

        return {
            "status": "success",
            "total_lines": total_lines,
            "range": [s_idx, e_idx],
            "output": "\n".join(formatted_output),
            "raw_content": raw_selected_text,
            "exit_code": 0
        }
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] Failed to read file: {str(e)}", "exit_code": -1}

def get_workspace_git_diff(path: str = "") -> dict:
    """
    檢視工作區相對於 Git 的 diff，避免盲改或遺漏除錯程式碼。
    """
    try:
        target_dir = (Path(WORKSPACE_DIR) / path).resolve() if path else Path(WORKSPACE_DIR).resolve()
        workspace_path = Path(WORKSPACE_DIR).resolve()
        if not str(target_dir).startswith(str(workspace_path)):
            return {"status": "error", "output": "[Bridge] Path out of workspace", "exit_code": -1}

        res = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=str(target_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        if res.returncode == 0:
            diff_output = res.stdout.strip()
            return {
                "status": "success",
                "output": diff_output or "[No Git Diffs - Working tree clean]",
                "exit_code": 0
            }
        else:
            # 若環境未安裝 git 或非 git repo
            return {
                "status": "error",
                "output": f"[Bridge] git diff 執行失敗: {res.stderr.strip() or 'Exit code ' + str(res.returncode)}",
                "exit_code": res.returncode
            }
    except FileNotFoundError:
        return {
            "status": "error",
            "output": "[Bridge] 系統未安裝 git CLI，無法執行 git diff。",
            "exit_code": -1
        }
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] 取得 git diff 異常: {str(e)}", "exit_code": -1}
