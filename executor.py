import uuid
import ast
import os
import stat
import subprocess
import difflib
import shutil
import re
from pathlib import Path
from typing import Optional
from config import WORKSPACE_DIR, MAX_OUTPUT_CHARS, DEFAULT_TIMEOUT_SEC

# 容器映像檔（包含常用執行環境）
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

async def patch_and_test_file(path: str, target: str, replacement: str, test_command: str, timeout: int = DEFAULT_TIMEOUT_SEC, auto_rollback: bool = False) -> dict:
    """
    原子操作：精確替換內容 -> 語法驗證 -> 即時執行測試指令。
    若 auto_rollback 為 True 且測試失敗，則自動還原原檔。
    """
    target_path = (Path(WORKSPACE_DIR) / path).resolve()
    original_content = None
    if target_path.exists() and target_path.is_file():
        try:
            original_content = target_path.read_text(encoding='utf-8')
        except Exception:
            pass

    replace_res = replace_file_content(path, target, replacement)
    if replace_res.get("status") != "success":
        return {
            "status": "failed",
            "patch_applied": False,
            "file_path": path,
            "error": replace_res.get("output"),
            "output": f"[patch_and_test] 替換階段失敗: {replace_res.get('output')}",
            "exit_code": replace_res.get("exit_code", -1)
        }

    test_res = await run_shell_command(test_command, timeout=timeout)
    test_status = test_res.get("status")
    test_exit_code = test_res.get("exit_code", 0)
    is_test_success = (test_status == "success" and test_exit_code == 0)

    rolled_back = False
    if not is_test_success and auto_rollback and original_content is not None:
        try:
            _ensure_writable(target_path)
            target_path.write_text(original_content, encoding='utf-8', newline='\n')
            rolled_back = True
        except Exception as e:
            rolled_back = f"還原失敗: {str(e)}"

    output_msg = f"[patch_and_test] 檔案已更新: {path}\n[測試指令] {test_command}\n[測試狀態] {test_status} (exit_code: {test_exit_code})\n[測試輸出]\n{test_res.get('output', '')}"
    if rolled_back is True:
        output_msg += "\n\n[Notice] 由於測試失敗且 auto_rollback=True，檔案已自動還原回原始狀態。"
    elif isinstance(rolled_back, str):
        output_msg += f"\n\n[Warning] {rolled_back}"

    return {
        "status": "success" if is_test_success else "failed",
        "patch_applied": True if not rolled_back else False,
        "rolled_back": rolled_back,
        "file_path": path,
        "test_execution": test_res,
        "output": output_msg,
        "exit_code": test_exit_code
    }

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
        stdout_text = (res.stdout or "").strip()
        stderr_text = (res.stderr or "").strip()
        if res.returncode == 0:
            return {
                "status": "success",
                "output": stdout_text or "[No Git Diffs - Working tree clean]",
                "exit_code": 0
            }
        else:
            # 若環境未安裝 git 或非 git repo
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

def list_workspace_dir(path: str = "", max_depth: int = 3) -> dict:
    """
    結構化掃描目錄樹，自動忽略 .git, __pycache__, node_modules, .venv 等噪音目錄，大幅節省 Token。
    """
    try:
        target_dir = (Path(WORKSPACE_DIR) / path).resolve() if path else Path(WORKSPACE_DIR).resolve()
        workspace_path = Path(WORKSPACE_DIR).resolve()
        if not str(target_dir).startswith(str(workspace_path)):
            return {"status": "error", "output": "[Bridge] Path out of workspace", "exit_code": -1}
        if not target_dir.exists() or not target_dir.is_dir():
            return {"status": "error", "output": f"[Bridge] Directory not found: {path}", "exit_code": -1}

        ignored_names = {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode"}
        tree_lines = []

        def _walk(current_dir: Path, prefix: str, depth: int):
            if depth > max_depth:
                return
            try:
                entries = sorted(list(current_dir.iterdir()), key=lambda e: (not e.is_dir(), e.name.lower()))
            except Exception:
                return
            filtered = [e for e in entries if e.name not in ignored_names and not e.name.startswith(".temp_")]
            count = len(filtered)
            for i, entry in enumerate(filtered):
                is_last = (i == count - 1)
                connector = "└── " if is_last else "├── "
                display_name = f"{entry.name}/" if entry.is_dir() else entry.name
                tree_lines.append(f"{prefix}{connector}{display_name}")
                if entry.is_dir():
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    _walk(entry, new_prefix, depth + 1)

        tree_lines.append(f"{target_dir.name or 'workspace'}/")
        _walk(target_dir, "", 1)

        return {
            "status": "success",
            "output": "\n".join(tree_lines),
            "exit_code": 0
        }
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] Failed to list dir: {str(e)}", "exit_code": -1}

def get_file_outline(path: str) -> dict:
    """
    基於 AST 快速解析 Python 檔案符號大綱（Class / Function / Method）及其所在行號。
    """
    try:
        target_path = (Path(WORKSPACE_DIR) / path).resolve()
        workspace_path = Path(WORKSPACE_DIR).resolve()
        if not str(target_path).startswith(str(workspace_path)):
            return {"status": "error", "output": "[Bridge] Path out of workspace", "exit_code": -1}
        if not target_path.exists() or not target_path.is_file():
            return {"status": "error", "output": f"[Bridge] File not found: {path}", "exit_code": -1}
        if not path.endswith(".py"):
            return {"status": "error", "output": "[Bridge] get_outline 目前僅支援 Python (.py) 原始碼檔案。", "exit_code": -1}

        content = target_path.read_text(encoding='utf-8')
        try:
            tree = ast.parse(content, filename=path)
        except SyntaxError as se:
            return {"status": "error", "output": f"[Bridge] 語法錯誤解析失敗: line {se.lineno}: {se.msg}", "exit_code": -1}

        outline_items = []

        def _extract(node, depth=0):
            indent = "  " * depth
            for child in getattr(node, "body", []):
                if isinstance(child, ast.ClassDef):
                    line = getattr(child, "lineno", 0)
                    end_line = getattr(child, "end_lineno", line)
                    outline_items.append(f"{indent}class {child.name} (L{line}-L{end_line})")
                    _extract(child, depth + 1)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    line = getattr(child, "lineno", 0)
                    end_line = getattr(child, "end_lineno", line)
                    prefix_type = "async def" if isinstance(child, ast.AsyncFunctionDef) else "def"
                    args = [a.arg for a in child.args.args]
                    outline_items.append(f"{indent}{prefix_type} {child.name}({', '.join(args)}) (L{line}-L{end_line})")
                    _extract(child, depth + 1)

        _extract(tree, 0)
        output_text = "\n".join(outline_items) if outline_items else "[No classes or functions found]"

        return {
            "status": "success",
            "output": output_text,
            "exit_code": 0
        }
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] Failed to get outline: {str(e)}", "exit_code": -1}

def search_codebase(query: str, path: str = "", include_pattern: str = "", max_results: int = 50) -> dict:
    """
    全專案文字或正則檢索。優先使用 ripgrep (rg)，若無則回退至 Python 原生目錄走訪。
    """
    try:
        target_dir = (Path(WORKSPACE_DIR) / path).resolve() if path else Path(WORKSPACE_DIR).resolve()
        workspace_path = Path(WORKSPACE_DIR).resolve()
        if not str(target_dir).startswith(str(workspace_path)):
            return {"status": "error", "output": "[Bridge] Path out of workspace", "exit_code": -1}
        if not target_dir.exists():
            return {"status": "error", "output": f"[Bridge] Path not found: {path}", "exit_code": -1}

        results = []
        rg_path = shutil.which("rg")
        if rg_path:
            cmd = [rg_path, "--line-number", "--no-heading", "--color=never", "--max-count", str(max_results)]
            for ignored in [".git", "node_modules", "__pycache__", ".venv", "venv", "target", "dist"]:
                cmd.extend(["-g", f"!{ignored}"])
            if include_pattern:
                cmd.extend(["-g", include_pattern])
            cmd.extend(["--", query, str(target_dir)])
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15
            )
            if res.stdout:
                rg_line_regex = re.compile(r"^(.*?):(\d+):(.*)$")
                for line in res.stdout.splitlines()[:max_results]:
                    match = rg_line_regex.match(line)
                    if match:
                        file_path_str, line_num, content = match.group(1), match.group(2), match.group(3)
                        try:
                            rel_f = str(Path(file_path_str).resolve().relative_to(workspace_path)).replace("\\", "/")
                        except ValueError:
                            rel_f = file_path_str.replace("\\", "/")
                        results.append({"file": rel_f, "line": int(line_num), "content": content.strip()})
        else:
            # Python 原生回退走訪
            ignored_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "target", "dist"}
            pattern = re.compile(query, re.IGNORECASE)
            glob_pat = include_pattern if include_pattern else "*"
            for item in target_dir.rglob(glob_pat):
                if len(results) >= max_results:
                    break
                if not item.is_file() or any(p in item.parts for p in ignored_dirs):
                    continue
                try:
                    lines = item.read_text(encoding="utf-8", errors="ignore").splitlines()
                    for idx, line in enumerate(lines, start=1):
                        if pattern.search(line):
                            rel_f = str(item.resolve().relative_to(workspace_path)).replace("\\", "/")
                            results.append({"file": rel_f, "line": idx, "content": line.strip()})
                            if len(results) >= max_results:
                                break
                except Exception:
                    continue

        return {
            "status": "success",
            "matches_count": len(results),
            "results": results,
            "exit_code": 0
        }
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] Search codebase failed: {str(e)}", "exit_code": -1}

def find_references(symbol: str, file_type: str = "", scope_dir: str = "") -> dict:
    """
    尋找特定符號（Class / Function / Method / Variable）之定義處與使用處。
    """
    try:
        target_dir = (Path(WORKSPACE_DIR) / scope_dir).resolve() if scope_dir else Path(WORKSPACE_DIR).resolve()
        workspace_path = Path(WORKSPACE_DIR).resolve()
        if not str(target_dir).startswith(str(workspace_path)):
            return {"status": "error", "output": "[Bridge] Path out of workspace", "exit_code": -1}
        if not symbol or not symbol.strip():
            return {"status": "error", "output": "[Bridge] symbol 參數不能為空", "exit_code": -1}

        ignored_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "target", "dist"}
        glob_pat = f"*.{file_type.lstrip('.')}" if file_type else "*"
        sym_regex = re.compile(rf"\b{re.escape(symbol.strip())}\b")
        def_regex = re.compile(rf"\b(class|def|async\s+def|function|interface|type|struct|fn|enum|record)\s+{re.escape(symbol.strip())}\b")

        definitions = []
        usages = []

        for item in target_dir.rglob(glob_pat):
            if not item.is_file() or any(p in item.parts for p in ignored_dirs):
                continue
            try:
                lines = item.read_text(encoding="utf-8", errors="ignore").splitlines()
                for idx, line in enumerate(lines, start=1):
                    if sym_regex.search(line):
                        rel_f = str(item.resolve().relative_to(workspace_path)).replace("\\", "/")
                        entry = {"file": rel_f, "line": idx, "content": line.strip()}
                        if def_regex.search(line):
                            definitions.append(entry)
                        else:
                            usages.append(entry)
            except Exception:
                continue

        return {
            "status": "success",
            "symbol": symbol,
            "definitions": definitions,
            "usages": usages,
            "exit_code": 0
        }
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] Find references failed: {str(e)}", "exit_code": -1}
