import ast
import re
import shutil
import subprocess
from pathlib import Path
from config import WORKSPACE_DIR, resolve_scoped_path, get_scoped_workspace_dir

def list_workspace_dir(path: str = "", max_depth: int = 3) -> dict:
    """
    結構化掃描目錄樹，自動忽略 .git, __pycache__, node_modules 等噪音目錄。
    """
    try:
        target_dir, base_scope = resolve_scoped_path(path)
        if not str(target_dir).startswith(str(base_scope)):
            return {"status": "error", "output": f"[Bridge Security] Path out of scoped workspace ({base_scope})", "exit_code": -1}
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
        target_path, base_scope = resolve_scoped_path(path)
        if not str(target_path).startswith(str(base_scope)):
            return {"status": "error", "output": f"[Bridge Security] Path out of scoped workspace ({base_scope})", "exit_code": -1}
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
        target_dir, base_scope = resolve_scoped_path(path)
        if not str(target_dir).startswith(str(base_scope)):
            return {"status": "error", "output": f"[Bridge Security] Path out of scoped workspace ({base_scope})", "exit_code": -1}
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
            try:
                res = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15
                )
            except subprocess.TimeoutExpired:
                return {"status": "timeout", "output": "搜尋執行逾時 (15s)", "matches_count": 0, "results": [], "exit_code": -1}
            if res.stdout:
                rg_line_regex = re.compile(r"^(.*?):(\d+):(.*)$")
                for line in res.stdout.splitlines()[:max_results]:
                    match = rg_line_regex.match(line)
                    if match:
                        file_path_str, line_num, content = match.group(1), match.group(2), match.group(3)
                        try:
                            rel_f = str(Path(file_path_str).resolve().relative_to(base_scope)).replace("\\", "/")
                        except ValueError:
                            rel_f = file_path_str.replace("\\", "/")
                        results.append({"file": rel_f, "line": int(line_num), "content": content.strip()})
        else:
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
                            rel_f = str(item.resolve().relative_to(base_scope)).replace("\\", "/")
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
        target_dir, base_scope = resolve_scoped_path(scope_dir)
        if not str(target_dir).startswith(str(base_scope)):
            return {"status": "error", "output": f"[Bridge Security] Path out of scoped workspace ({base_scope})", "exit_code": -1}
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
                        rel_f = str(item.resolve().relative_to(base_scope)).replace("\\", "/")
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
