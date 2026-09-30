import ast
import json
import re
import shutil
import subprocess
import threading
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import resolve_scoped_path

IGNORED_DIRS = [".git", "node_modules", "__pycache__", ".venv", "venv", "target", "dist", ".idea", ".vscode"]
MAX_LINE_LENGTH = 300

def list_workspace_dir(path: str = "", max_depth: int = 3) -> dict:
    """
    結構化掃描目錄樹，自動忽略 .git, __pycache__, node_modules 等噪音目錄。
    """
    try:
        target_dir, base_scope = resolve_scoped_path(path)
        target_dir, base_scope = target_dir.resolve(), base_scope.resolve()
        if not target_dir.is_relative_to(base_scope):
            return {"status": "error", "output": f"[Bridge Security] Path out of scoped workspace ({base_scope})", "exit_code": -1}
        if not target_dir.exists() or not target_dir.is_dir():
            return {"status": "error", "output": f"[Bridge] Directory not found: {path}", "exit_code": -1}

        ignored_names = set(IGNORED_DIRS)
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

@lru_cache(maxsize=1024)
def _ctags_parse(abs_path: str, mtime_ns: int) -> list:
    """調用 universal-ctags 提取符號資訊（支援 C、C++、Assembly、Rust 等多語言）"""
    ctags_bin = shutil.which("ctags")
    if not ctags_bin:
        return []
    cmd = [
        ctags_bin,
        "--output-format=json",
        "--fields=+neKSs",
        "--kinds-C=+p",
        "--map-Asm=+.inc",
        "-f", "-",
        abs_path
    ]
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10
        )
    except Exception:
        return []

    tags = []
    for ln in res.stdout.splitlines():
        try:
            t = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if t.get("_type") != "tag":
            continue
        name = t.get("name", "")
        # 過濾 assembly 內部暫存 label (如 .L123, 1:)
        if name.startswith(".L") or name.isdigit():
            continue
        line = t.get("line", 0)
        end = t.get("end")
        tags.append({
            "name": name,
            "kind": t.get("kind", ""),
            "line": line,
            "end": end,
            "scope": t.get("scope", ""),
            "signature": t.get("signature", "")
        })

    tags.sort(key=lambda x: x["line"])
    for i, t in enumerate(tags):
        if not t.get("end"):
            t["end"] = tags[i + 1]["line"] - 1 if i + 1 < len(tags) else t["line"]
    return tags

def _get_file_tags(file_path: Path) -> list:
    """取得檔案的符號清單。Python 優先使用內建 AST，其餘使用 ctags"""
    try:
        if not file_path.exists() or not file_path.is_file():
            return []
        if file_path.suffix == ".py":
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            tree = ast.parse(content, filename=str(file_path))
            tags = []
            def _extract_py(node, parent_scope=""):
                for child in getattr(node, "body", []):
                    if isinstance(child, ast.ClassDef):
                        scope = f"{parent_scope}.{child.name}" if parent_scope else child.name
                        tags.append({
                            "name": child.name,
                            "kind": "class",
                            "line": getattr(child, "lineno", 0),
                            "end": getattr(child, "end_lineno", getattr(child, "lineno", 0)),
                            "scope": parent_scope
                        })
                        _extract_py(child, scope)
                    elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        prefix_type = "async_function" if isinstance(child, ast.AsyncFunctionDef) else "function"
                        tags.append({
                            "name": child.name,
                            "kind": prefix_type,
                            "line": getattr(child, "lineno", 0),
                            "end": getattr(child, "end_lineno", getattr(child, "lineno", 0)),
                            "scope": parent_scope
                        })
                        _extract_py(child, f"{parent_scope}.{child.name}" if parent_scope else child.name)
            _extract_py(tree)
            tags.sort(key=lambda x: x["line"])
            return tags
        else:
            mtime = file_path.stat().st_mtime_ns
            return _ctags_parse(str(file_path.resolve()), mtime)
    except Exception:
        return []

def enclosing_symbol(tags: list, line: int) -> Optional[dict]:
    """回傳包含該行、範圍最窄的函式/類別/label"""
    relevant_kinds = {"function", "async_function", "class", "method", "member", "label", "macro", "struct", "prototype"}
    hits = [t for t in tags if t.get("kind") in relevant_kinds and t["line"] <= line <= t.get("end", line)]
    if not hits:
        return None
    return min(hits, key=lambda t: t.get("end", line) - t["line"])

def get_file_outline(path: str) -> dict:
    """
    解析原始碼檔案符號大綱（Class / Function / Method / Label）及其所在行號。
    """
    try:
        target_path, base_scope = resolve_scoped_path(path)
        target_path, base_scope = target_path.resolve(), base_scope.resolve()
        if not target_path.is_relative_to(base_scope):
            return {"status": "error", "output": f"[Bridge Security] Path out of scoped workspace ({base_scope})", "exit_code": -1}
        if not target_path.exists() or not target_path.is_file():
            return {"status": "error", "output": f"[Bridge] File not found: {path}", "exit_code": -1}

        tags = _get_file_tags(target_path)
        if not tags:
            if target_path.suffix != ".py" and not shutil.which("ctags"):
                return {
                    "status": "error",
                    "output": "[Bridge] 未檢測到 universal-ctags 工具，非 Python 檔案無法生成 outline。請於環境安裝 universal-ctags。",
                    "exit_code": -1
                }
            return {"status": "success", "output": "[No classes, functions, or labels found]", "exit_code": 0}

        outline_items = []
        for t in tags:
            scope_prefix = f"{t['scope']}." if t.get('scope') else ""
            kind_display = t.get('kind', 'sym')
            outline_items.append(f"{kind_display} {scope_prefix}{t['name']} (L{t['line']}-L{t['end']})")

        return {
            "status": "success",
            "total_symbols": len(tags),
            "output": "\n".join(outline_items),
            "tags": tags,
            "exit_code": 0
        }
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] Failed to get outline: {str(e)}", "exit_code": -1}

def search_codebase(
    query: str,
    path: str = "",
    include_pattern: str = "",
    max_results: int = 50,
    offset: int = 0,
    context_lines: int = 2,
    fixed_strings: bool = False,
    case_sensitive: Optional[bool] = None
) -> dict:
    """
    全專案文字或正則檢索。
    - 優先使用 ripgrep (rg) 並以 --json 解析，具備安全沙盒與穩健容錯。
    - fixed_strings=True 時當作純字面字串（避免括號、點號正則誤配）。
    - case_sensitive: None=smart-case, True=區分大小寫, False=不區分大小寫。
    - 單行防爆保護 (MAX_LINE_LENGTH = 300) 並註記 enclosing symbol。
    """
    try:
        target_dir, base_scope = resolve_scoped_path(path)
        target_dir, base_scope = target_dir.resolve(), base_scope.resolve()
        if not target_dir.is_relative_to(base_scope):
            return {"status": "error", "output": f"[Bridge Security] Path out of scoped workspace ({base_scope})", "exit_code": -1}
        if not target_dir.exists():
            return {"status": "error", "output": f"[Bridge] Path not found: {path}", "exit_code": -1}

        rg_path = shutil.which("rg")
        results = []
        truncated = False

        if rg_path:
            cmd = [rg_path, "--json", "--no-messages", "--sort=path"]
            if fixed_strings:
                cmd.append("-F")
            if case_sensitive is True:
                cmd.append("-s")
            elif case_sensitive is False:
                cmd.append("-i")
            else:
                cmd.append("-S")  # Smart-case

            if context_lines > 0:
                cmd.extend(["-C", str(context_lines)])

            for ignored in IGNORED_DIRS:
                cmd.extend(["-g", f"!{ignored}/"])

            if include_pattern:
                cmd.extend(["-g", include_pattern])

            cmd.extend(["--", query, str(target_dir)])

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            timed_out = threading.Event()
            timer = threading.Timer(15, lambda: (timed_out.set(), proc.kill()))
            timer.start()

            seen = 0
            tags_cache = {}
            try:
                for raw in proc.stdout:
                    try:
                        ev = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("type") != "match":
                        continue
                    seen += 1
                    if seen <= offset:
                        continue
                    if len(results) >= max_results:
                        truncated = True
                        proc.kill()
                        break

                    d = ev.get("data", {})
                    fpath_raw = d.get("path", {}).get("text", "")
                    fpath = Path(fpath_raw).resolve()
                    try:
                        rel_f = fpath.relative_to(base_scope).as_posix()
                    except ValueError:
                        rel_f = fpath.as_posix()

                    line_num = d.get("line_number", 0)
                    lines_dict = d.get("lines", {})
                    line_text = lines_dict.get("text", "").rstrip("\r\n")
                    if len(line_text) > MAX_LINE_LENGTH:
                        line_text = line_text[:MAX_LINE_LENGTH] + "... [TRUNCATED]"

                    # 計算 Enclosing Symbol
                    if rel_f not in tags_cache:
                        tags_cache[rel_f] = _get_file_tags(fpath)
                    enc = enclosing_symbol(tags_cache[rel_f], line_num)
                    enclosing_desc = f"{enc.get('kind', 'sym')} {enc.get('name')} (L{enc.get('line')}-L{enc.get('end')})" if enc else ""

                    res_item = {
                        "file": rel_f,
                        "line": line_num,
                        "content": line_text.strip()
                    }
                    if enclosing_desc:
                        res_item["enclosing"] = enclosing_desc
                    results.append(res_item)
                proc.wait()
            finally:
                timer.cancel()

            if timed_out.is_set():
                return {
                    "status": "timeout",
                    "output": "搜尋逾時 (15s)，請縮小 path 或 include_pattern",
                    "results": results,
                    "truncated": True,
                    "exit_code": -1
                }
            if proc.returncode == 2 and not results:
                err_msg = proc.stderr.read().strip()
                return {"status": "error", "output": f"rg error: {err_msg}", "exit_code": -1}

        else:
            # Python 原生目錄走訪 Fallback (附帶警告訊息)
            flags = 0 if case_sensitive is True else re.IGNORECASE
            re_query = re.escape(query) if fixed_strings else query
            try:
                pattern = re.compile(re_query, flags)
            except re.error as re_err:
                return {"status": "error", "output": f"正則表達式錯誤: {re_err}", "exit_code": -1}

            glob_pat = include_pattern if include_pattern else "*"
            seen = 0
            tags_cache = {}
            for item in sorted(list(target_dir.rglob(glob_pat))):
                if not item.is_file() or any(p in item.parts for p in IGNORED_DIRS):
                    continue
                try:
                    lines = item.read_text(encoding="utf-8", errors="ignore").splitlines()
                    for idx, line in enumerate(lines, start=1):
                        if pattern.search(line):
                            seen += 1
                            if seen <= offset:
                                continue
                            if len(results) >= max_results:
                                truncated = True
                                break
                            rel_f = item.resolve().relative_to(base_scope).as_posix()
                            line_text = line.strip()
                            if len(line_text) > MAX_LINE_LENGTH:
                                line_text = line_text[:MAX_LINE_LENGTH] + "... [TRUNCATED]"

                            if rel_f not in tags_cache:
                                tags_cache[rel_f] = _get_file_tags(item)
                            enc = enclosing_symbol(tags_cache[rel_f], idx)
                            enclosing_desc = f"{enc.get('kind', 'sym')} {enc.get('name')} (L{enc.get('line')}-L{enc.get('end')})" if enc else ""

                            res_item = {
                                "file": rel_f,
                                "line": idx,
                                "content": line_text
                            }
                            if enclosing_desc:
                                res_item["enclosing"] = enclosing_desc
                            results.append(res_item)
                except Exception:
                    continue
                if truncated:
                    break

        out = {
            "status": "success",
            "matches_count": len(results),
            "truncated": truncated,
            "results": results,
            "exit_code": 0
        }
        if not rg_path:
            out["warning"] = "[Bridge] 系統未安裝 ripgrep (rg)，已自動降級使用 Python 目錄搜尋。建議安裝 ripgrep 以獲得最高效能。"
        if truncated:
            out["hint"] = f"還有更多結果。可用 offset={offset + max_results} 翻頁，或指定 path / include_pattern 縮小範圍。"
        return out
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] Search codebase failed: {str(e)}", "exit_code": -1}

def grep_code(
    query: str,
    path: str = "",
    include_pattern: str = "",
    context_lines: int = 2,
    max_results: int = 50,
    offset: int = 0,
    fixed_strings: bool = False,
    case_sensitive: Optional[bool] = None
) -> dict:
    """grep_code: 精準程式碼關鍵字或正則檢索 (search_codebase 的首選標準介面)"""
    return search_codebase(
        query=query,
        path=path,
        include_pattern=include_pattern,
        max_results=max_results,
        offset=offset,
        context_lines=context_lines,
        fixed_strings=fixed_strings,
        case_sensitive=case_sensitive
    )

def find_definition(symbol: str, path: str = "", file_type: str = "") -> dict:
    """
    精確定位函式 (def/fn)、類別 (class/struct/interface)、組合語言 label 等宣告定義。
    - 策略：以候選檔案集合比對 outline/ctags，並支援 C/Asm 前綴底線相容性 (_symbol)。
    """
    try:
        target_dir, base_scope = resolve_scoped_path(path)
        target_dir, base_scope = target_dir.resolve(), base_scope.resolve()
        if not target_dir.is_relative_to(base_scope):
            return {"status": "error", "output": f"[Bridge Security] Path out of scoped workspace ({base_scope})", "exit_code": -1}
        if not symbol or not symbol.strip():
            return {"status": "error", "output": "[Bridge] symbol 參數不能為空", "exit_code": -1}

        clean_sym = symbol.strip()
        names = {clean_sym, "_" + clean_sym}
        include_pat = f"*.{file_type.lstrip('.')}" if file_type else ""

        # 先透過 search_codebase 快速篩選候選檔案
        search_res = search_codebase(clean_sym, path=path, include_pattern=include_pat, fixed_strings=True, max_results=300)
        candidate_files = {item["file"] for item in search_res.get("results", [])}

        definitions = []
        for rel in sorted(list(candidate_files)):
            fpath = (base_scope / rel).resolve()
            tags = _get_file_tags(fpath)
            for t in tags:
                if t.get("name") in names:
                    definitions.append({
                        "file": rel,
                        "name": t.get("name"),
                        "kind": t.get("kind"),
                        "line": t.get("line"),
                        "end": t.get("end"),
                        "signature": t.get("signature", ""),
                        "scope": t.get("scope", "")
                    })

        # 若 ctags 未找到定義（或未安裝 ctags），降級使用常見宣告正則雙重保障
        if not definitions:
            def_pat = re.compile(rf"^\s*(class|def|async\s+def|func|fn|function|interface|type|struct|enum|record)\s+{re.escape(clean_sym)}\b|\b{re.escape(clean_sym)}:\s*$")
            for item in search_res.get("results", []):
                if def_pat.search(item.get("content", "")):
                    definitions.append({
                        "file": item["file"],
                        "name": clean_sym,
                        "kind": "definition",
                        "line": item["line"],
                        "end": item["line"],
                        "content": item.get("content")
                    })

        return {
            "status": "success",
            "symbol": clean_sym,
            "definitions_count": len(definitions),
            "definitions": definitions,
            "suggestion": f"若需要查看定義詳細邏輯，請呼叫 file_read(path='{definitions[0]['file']}', start_line={definitions[0]['line']}, end_line={definitions[0]['end']})" if definitions else "未找到宣告定義",
            "exit_code": 0
        }
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] Find definition failed: {str(e)}", "exit_code": -1}

def find_references(symbol: str, path: str = "", file_type: str = "") -> dict:
    """
    跨語言符號引用查詢，自動分類 definition / call / branch (jmp/call/bl) / usage。
    """
    try:
        target_dir, base_scope = resolve_scoped_path(path)
        target_dir, base_scope = target_dir.resolve(), base_scope.resolve()
        if not target_dir.is_relative_to(base_scope):
            return {"status": "error", "output": f"[Bridge Security] Path out of scoped workspace ({base_scope})", "exit_code": -1}
        if not symbol or not symbol.strip():
            return {"status": "error", "output": "[Bridge] symbol 參數不能為空", "exit_code": -1}

        clean_sym = symbol.strip()
        include_pat = f"*.{file_type.lstrip('.')}" if file_type else ""
        # 檢索所有符號出現處（含單詞邊界）
        search_res = search_codebase(rf"\b_?{re.escape(clean_sym)}\b", path=path, include_pattern=include_pat, max_results=200)
        if search_res.get("status") != "success":
            return search_res

        definitions = []
        calls = []
        branches = []
        usages = []

        branch_regex = re.compile(rf"\b(call|jmp|j[a-z]{{1,3}}|bl|bx|blx|rcall|rjmp)\s+_?{re.escape(clean_sym)}\b", re.IGNORECASE)
        def_regex = re.compile(rf"^\s*(class|def|async\s+def|func|fn|function|interface|type|struct|enum|record)\s+{re.escape(clean_sym)}\b|\b{re.escape(clean_sym)}:\s*$")
        call_regex = re.compile(rf"\b{re.escape(clean_sym)}\s*\(")

        for item in search_res.get("results", []):
            content = item.get("content", "")
            if def_regex.search(content):
                definitions.append(item)
            elif branch_regex.search(content):
                branches.append(item)
            elif call_regex.search(content):
                calls.append(item)
            else:
                usages.append(item)

        return {
            "status": "success",
            "symbol": clean_sym,
            "total_references": len(search_res.get("results", [])),
            "definitions": definitions,
            "calls": calls,
            "branches": branches,
            "usages": usages,
            "exit_code": 0
        }
    except Exception as e:
        return {"status": "error", "output": f"[Bridge] Find references failed: {str(e)}", "exit_code": -1}
