import ast
import stat
import subprocess
from pathlib import Path
from typing import Optional
from config import WORKSPACE_DIR, resolve_scoped_path, get_scoped_workspace_dir

def _resolve_and_guard(path: str = "") -> tuple[Path, Optional[dict]]:
    """根據當前 scoped project 解析目標路徑並實施沙盒邊界隔離防護"""
    target_path, base_scope = resolve_scoped_path(path)
    if not str(target_path).startswith(str(base_scope)):
        return target_path, {"status": "error", "output": f"[Bridge Security] Path traversal detected: 路徑超出當前工作專案邊界 ({base_scope})", "exit_code": -1}
    return target_path, None

def _ensure_writable(path_obj: Path):
    """嘗試解除 Docker root 產生的唯讀標記或修復權限"""
    try:
        if path_obj.exists():
            current_mode = path_obj.stat().st_mode
            path_obj.chmod(current_mode | stat.S_IWRITE | stat.S_IREAD)
    except Exception:
        pass

def validate_python_syntax(file_path: str, code_content: str) -> Optional[str]:
    """若為 .py 檔，檢查 Python AST 語法合法性，避免語法錯誤落地"""
    if file_path.endswith(".py"):
        try:
            ast.parse(code_content, filename=file_path)
        except SyntaxError as se:
            return f"[Bridge] Python 語法驗證失敗 (行 {se.lineno}, 列 {se.offset}): {se.msg}"
    return None

def write_workspace_file(path: str, content: str) -> dict:
    try:
        target_path, err = _resolve_and_guard(path)
        if err:
            return err
        
        normalized_content = content.replace("\r\n", "\n").replace("\r", "\n")
        
        syntax_err = validate_python_syntax(path, normalized_content)
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
        target_path, err = _resolve_and_guard(path)
        if err:
            return err
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
        
        syntax_err = validate_python_syntax(path, updated_content)
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

def read_workspace_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> dict:
    """
    結構化讀取工作區檔案，支援指定行號範圍並附帶行號。
    """
    try:
        target_path, err = _resolve_and_guard(path)
        if err:
            return err
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
    檢視工作區相對於 Git 的 diff。
    """
    try:
        target_path = (Path(WORKSPACE_DIR) / path).resolve() if path else Path(WORKSPACE_DIR).resolve()
        workspace_path = Path(WORKSPACE_DIR).resolve()
        if not str(target_path).startswith(str(workspace_path)):
            return {"status": "error", "output": "[Bridge] Path out of workspace", "exit_code": -1}

        if target_path.is_file():
            cwd_dir = target_path.parent
            cmd = ["git", "diff", "HEAD", "--", target_path.name]
        else:
            cwd_dir = target_path
            cmd = ["git", "diff", "HEAD"]

        res = subprocess.run(
            cmd,
            cwd=str(cwd_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10
        )
        stdout_text = (res.stdout or "").strip()
        stderr_text = (res.stderr or "").strip()
        if res.returncode == 0:
            return {
                "status": "success",
                "output": stdout_text or "[No Git Diffs - Working tree clean]",
                "exit_code": 0
            }
        else:
            return {
                "status": "error",
                "output": f"[Bridge] git diff 執行失敗: {stderr_text or 'Exit code ' + str(res.returncode)}",
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
