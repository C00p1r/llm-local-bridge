import os
import shutil
import subprocess
import json
import asyncio
import base64
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, List
from config import WORKSPACE_DIR, GITHUB_TOKEN

AVAILABLE_ACTIONS = {
    "pull": "Pull changes from remote repository (params: subfolder, remote, branch, force_reset)",
    "fetch": "Fetch refs from remote repository (params: subfolder, remote)",
    "clone": "Clone a repository into workspace (params: repo_url, target_subfolder)",
    "push": "Commit and push workspace/subfolder to GitHub via API (params: repo, branch, message, subfolder)",
    "push_workspace": "Alias for push (params: repo, branch, message, subfolder)",
    "status": "Get working directory status (params: subfolder)",
    "log": "Get commit history log (params: subfolder, max_count, oneline, file_path)",
    "blame": "Show what revision and author last modified each line of a file (params: file_path, start_line, end_line, subfolder)",
    "branch": "List, create, or switch branches (params: action, branch_name, subfolder)",
    "checkout": "Switch branches or restore working tree files (params: branch_name, create_branch, file_path, subfolder)",
    "clean": "Remove untracked files from working tree (params: subfolder, dry_run)",
    "list_actions": "List all available github actions and their descriptions"
}

def list_available_actions() -> Dict[str, Any]:
    return {
        "status": "success",
        "actions": AVAILABLE_ACTIONS
    }

def get_git_executable() -> str:
    git_path = shutil.which("git")
    if not git_path:
        raise FileNotFoundError("系統環境中未找到 git 指令，請確認是否安裝 Git 並加入 PATH")
    return git_path

def _resolve_target_path(subfolder: str = "") -> Path:
    return (WORKSPACE_DIR / subfolder).resolve() if subfolder else WORKSPACE_DIR

def git_clone(repo_url: str, target_subfolder: str = "") -> Dict[str, Any]:
    try:
        git_bin = get_git_executable()
        target_path = _resolve_target_path(target_subfolder)
        if target_path.exists() and any(target_path.iterdir()):
            return {"status": "error", "output": f"目標目錄已存在且不為空: {target_path}", "exit_code": -1}
        target_path.mkdir(parents=True, exist_ok=True)
        cmd = [git_bin, "clone", repo_url, str(target_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if res.returncode == 0:
            return {"status": "success", "output": res.stdout or f"成功 Clone 至 {target_path}", "exit_code": 0}
        else:
            return {"status": "failed", "output": res.stderr, "exit_code": res.returncode}
    except Exception as e:
        return {"status": "error", "output": str(e), "exit_code": -1}

def git_fetch(subfolder: str = "", remote: str = "origin") -> Dict[str, Any]:
    try:
        git_bin = get_git_executable()
        target_path = _resolve_target_path(subfolder)
        if not (target_path / ".git").exists():
            return {"status": "error", "output": f"目錄 {target_path} 不是有效的 Git 倉庫", "exit_code": -1}
        cmd = [git_bin, "fetch", remote]
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        if res.returncode == 0:
            return {"status": "success", "output": res.stdout or f"成功 Fetch {remote}", "exit_code": 0}
        else:
            return {"status": "failed", "output": res.stderr, "exit_code": res.returncode}
    except Exception as e:
        return {"status": "error", "output": str(e), "exit_code": -1}

def git_pull(subfolder: str = "", remote: str = "origin", branch: str = "main", force_reset: bool = False) -> Dict[str, Any]:
    try:
        git_bin = get_git_executable()
        target_path = _resolve_target_path(subfolder)
        if not (target_path / ".git").exists():
            return {"status": "error", "output": f"目錄 {target_path} 不是有效的 Git 倉庫", "exit_code": -1}
        if force_reset:
            subprocess.run([git_bin, "fetch", remote], cwd=str(target_path), capture_output=True, timeout=30)
            reset_cmd = [git_bin, "reset", "--hard", f"{remote}/{branch}"]
            res = subprocess.run(reset_cmd, cwd=str(target_path), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
            if res.returncode == 0:
                return {"status": "success", "output": f"已強制重設至 {remote}/{branch}", "exit_code": 0}
            else:
                return {"status": "failed", "output": res.stderr, "exit_code": res.returncode}
        else:
            pull_cmd = [git_bin, "pull", remote, branch]
            res = subprocess.run(pull_cmd, cwd=str(target_path), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
            if res.returncode == 0:
                return {"status": "success", "output": res.stdout or f"成功 Pull {remote}/{branch}", "exit_code": 0}
            else:
                return {"status": "failed", "output": res.stderr, "exit_code": res.returncode}
    except Exception as e:
        return {"status": "error", "output": str(e), "exit_code": -1}

def git_status(subfolder: str = "") -> Dict[str, Any]:
    try:
        git_bin = get_git_executable()
        target_path = _resolve_target_path(subfolder)
        if not (target_path / ".git").exists():
            return {"status": "error", "output": f"目錄 {target_path} 不是有效的 Git 倉庫", "exit_code": -1}
        cmd = [git_bin, "status", "-s", "-b"]
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        if res.returncode == 0:
            output = res.stdout.strip() or "工作區乾淨無修改 (working tree clean)"
            return {"status": "success", "output": output, "exit_code": 0}
        else:
            return {"status": "failed", "output": res.stderr, "exit_code": res.returncode}
    except Exception as e:
        return {"status": "error", "output": str(e), "exit_code": -1}

def git_log(subfolder: str = "", max_count: int = 10, oneline: bool = True, file_path: str = "") -> Dict[str, Any]:
    try:
        git_bin = get_git_executable()
        target_path = _resolve_target_path(subfolder)
        if not (target_path / ".git").exists():
            return {"status": "error", "output": f"目錄 {target_path} 不是有效的 Git 倉庫", "exit_code": -1}
        cmd = [git_bin, "log", f"-n{max_count}"]
        if oneline:
            cmd.append("--oneline")
        if file_path:
            cmd.extend(["--", file_path])
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        if res.returncode == 0:
            output = res.stdout.strip() or "無任何提交紀錄"
            return {"status": "success", "output": output, "exit_code": 0}
        else:
            return {"status": "failed", "output": res.stderr, "exit_code": res.returncode}
    except Exception as e:
        return {"status": "error", "output": str(e), "exit_code": -1}

def git_blame(file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None, subfolder: str = "") -> Dict[str, Any]:
    try:
        if not file_path:
            return {"status": "error", "output": "必須提供 file_path 參數", "exit_code": -1}
        git_bin = get_git_executable()
        target_path = _resolve_target_path(subfolder)
        if not (target_path / ".git").exists():
            return {"status": "error", "output": f"目錄 {target_path} 不是有效的 Git 倉庫", "exit_code": -1}
        cmd = [git_bin, "blame"]
        if start_line is not None and end_line is not None:
            cmd.extend(["-L", f"{start_line},{end_line}"])
        elif start_line is not None:
            cmd.extend(["-L", f"{start_line},{start_line}"])
        cmd.extend(["--", file_path])
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        if res.returncode == 0:
            return {"status": "success", "output": res.stdout.strip(), "exit_code": 0}
        else:
            return {"status": "failed", "output": res.stderr, "exit_code": res.returncode}
    except Exception as e:
        return {"status": "error", "output": str(e), "exit_code": -1}

def git_branch(action: str = "list", branch_name: str = "", subfolder: str = "") -> Dict[str, Any]:
    try:
        git_bin = get_git_executable()
        target_path = _resolve_target_path(subfolder)
        if not (target_path / ".git").exists():
            return {"status": "error", "output": f"目錄 {target_path} 不是有效的 Git 倉庫", "exit_code": -1}
        action = (action or "list").lower().strip()
        if action == "list":
            cmd = [git_bin, "branch", "-a"]
        elif action == "checkout":
            if not branch_name:
                return {"status": "error", "output": "checkout 操作必須提供 branch_name", "exit_code": -1}
            cmd = [git_bin, "checkout", branch_name]
        elif action == "create":
            if not branch_name:
                return {"status": "error", "output": "create 操作必須提供 branch_name", "exit_code": -1}
            cmd = [git_bin, "checkout", "-b", branch_name]
        else:
            return {"status": "error", "output": f"不支援的 branch action: {action}。可用操作: list, checkout, create", "exit_code": -1}
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        if res.returncode == 0:
            output = res.stdout.strip() or res.stderr.strip() or f"成功執行 branch {action}"
            return {"status": "success", "output": output, "exit_code": 0}
        else:
            return {"status": "failed", "output": res.stderr, "exit_code": res.returncode}
    except Exception as e:
        return {"status": "error", "output": str(e), "exit_code": -1}

def git_checkout(branch_name: str = "", create_branch: bool = False, file_path: str = "", subfolder: str = "") -> Dict[str, Any]:
    try:
        git_bin = get_git_executable()
        target_path = _resolve_target_path(subfolder)
        if not (target_path / ".git").exists():
            return {"status": "error", "output": f"目錄 {target_path} 不是有效的 Git 倉庫", "exit_code": -1}
        
        if file_path:
            cmd = [git_bin, "checkout", "--", file_path]
        elif branch_name:
            if create_branch:
                cmd = [git_bin, "checkout", "-b", branch_name]
            else:
                cmd = [git_bin, "checkout", branch_name]
        else:
            return {"status": "error", "output": "git_checkout 必須指定 branch_name 或 file_path", "exit_code": -1}
            
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        if res.returncode == 0:
            output = res.stdout.strip() or res.stderr.strip() or "成功執行 checkout"
            return {"status": "success", "output": output, "exit_code": 0}
        else:
            return {"status": "failed", "output": res.stderr, "exit_code": res.returncode}
    except Exception as e:
        return {"status": "error", "output": str(e), "exit_code": -1}

def git_clean(subfolder: str = "", dry_run: bool = False) -> Dict[str, Any]:
    try:
        git_bin = get_git_executable()
        target_path = _resolve_target_path(subfolder)
        if not (target_path / ".git").exists():
            return {"status": "error", "output": f"目錄 {target_path} 不是有效的 Git 倉庫", "exit_code": -1}
        flags = "-nd" if dry_run else "-fd"
        cmd = [git_bin, "clean", flags]
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        if res.returncode == 0:
            output = res.stdout.strip() or "無任何未追蹤檔案需要清理"
            return {"status": "success", "output": output, "exit_code": 0}
        else:
            return {"status": "failed", "output": res.stderr, "exit_code": res.returncode}
    except Exception as e:
        return {"status": "error", "output": str(e), "exit_code": -1}

def _github_api_request(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            status = response.getcode()
            text = response.read().decode("utf-8")
            return {"status_code": status, "data": json.loads(text) if text else {}, "raw": text}
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8")
        return {"status_code": e.code, "data": {}, "raw": text, "error": True}
    except Exception as e:
        return {"status_code": -1, "data": {}, "raw": str(e), "error": True}

async def _github_api_request_async(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return await asyncio.to_thread(_github_api_request, method, url, headers, payload)

async def _fetch_all_remote_tree_entries(api_base: str, tree_sha: str, headers: Dict[str, str]) -> Dict[str, str]:
    """遞迴抓取遠端 tree，建立 path -> sha 映射"""
    url = f"{api_base}/git/trees/{tree_sha}?recursive=1"
    res = await _github_api_request_async("GET", url, headers)
    if res.get("error") or "tree" not in res.get("data", {}):
        return {}
    return {
        item["path"]: item["sha"]
        for item in res["data"]["tree"]
        if item.get("type") == "blob" and "path" in item and "sha" in item
    }

async def push_workspace_to_github(repo: str, branch: str = "main", message: str = "Update from LLM Bridge", subfolder: str = "") -> Dict[str, Any]:
    if not GITHUB_TOKEN:
        return {"status": "error", "output": "未設定 GITHUB_TOKEN，無法使用 GitHub API 進行推送", "exit_code": -1}
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "LLM-Local-Bridge-Client"
    }
    api_base = f"https://api.github.com/repos/{repo}"

    ref_res = await _github_api_request_async("GET", f"{api_base}/git/ref/heads/{branch}", headers)
    if ref_res.get("error"):
        return {"status": "error", "output": f"獲取分支 {branch} 失敗: {ref_res.get('raw')}", "exit_code": -1}
    parent_commit_sha = ref_res["data"]["object"]["sha"]

    commit_res = await _github_api_request_async("GET", f"{api_base}/git/commits/{parent_commit_sha}", headers)
    if commit_res.get("error"):
        return {"status": "error", "output": f"獲取 Commit {parent_commit_sha} 失敗: {commit_res.get('raw')}", "exit_code": -1}
    base_tree_sha = commit_res["data"]["tree"]["sha"]

    # 取得遠端現有 tree 檔案 sha 快取，以達成差異比對 (避免全量重複上傳)
    remote_tree_map = await _fetch_all_remote_tree_entries(api_base, base_tree_sha, headers)

    target_path = _resolve_target_path(subfolder)

    # 1. 取得受版本控制或待追蹤的有效檔案清單 (嚴格遵循 .gitignore 與本地 git 設定)
    local_files: List[Path] = []
    git_bin = shutil.which("git")
    if git_bin and (target_path / ".git").exists():
        try:
            # 列出所有被追蹤或未被 .gitignore 排除的檔案 (相對於 target_path)
            cmd = [git_bin, "ls-files", "--cached", "--others", "--exclude-standard"]
            res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    line = line.strip()
                    if line:
                        full_p = target_path / line
                        if full_p.is_file():
                            local_files.append(full_p)
        except Exception:
            local_files = []

    # 若無 git 倉庫或 ls-files 失敗，以 filesystem walk 作為備援，但嚴格過濾常見快取與資料目錄
    if not local_files:
        ignored_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "target", "dist", ".idea", ".vscode", "data"}
        for root, dirs, files in os.walk(target_path):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            for f in files:
                local_files.append(Path(root) / f)

    if not local_files:
        return {"status": "error", "output": "沒有發現可推送的檔案", "exit_code": -1}

    # 2. 計算 Git Blob SHA 進行差異感知，僅針對變更或新增之檔案發送 API
    def _read_and_inspect_file(file_full: Path, rel_path: str):
        try:
            content_bytes = file_full.read_bytes()
            # Git blob sha1 計算: sha1("blob " + len + "\0" + bytes)
            import hashlib
            git_header = f"blob {len(content_bytes)}\0".encode("utf-8")
            local_sha = hashlib.sha1(git_header + content_bytes).hexdigest()
            remote_sha = remote_tree_map.get(rel_path)

            need_upload = (local_sha != remote_sha)
            blob_payload = None
            if need_upload:
                try:
                    blob_payload = {"content": content_bytes.decode("utf-8"), "encoding": "utf-8"}
                except UnicodeDecodeError:
                    blob_payload = {"content": base64.b64encode(content_bytes).decode("utf-8"), "encoding": "base64"}
            return rel_path, local_sha, need_upload, blob_payload
        except Exception:
            return rel_path, None, False, None

    file_diff_tasks = [
        asyncio.to_thread(_read_and_inspect_file, f, str(f.relative_to(target_path)).replace("\\", "/"))
        for f in local_files
    ]
    file_diff_results = await asyncio.gather(*file_diff_tasks)

    tree_items = []
    pending_uploads = []
    for rel_path, local_sha, need_upload, blob_payload in file_diff_results:
        if not local_sha:
            continue
        if need_upload and blob_payload:
            pending_uploads.append((rel_path, blob_payload))
        else:
            # 檔案內容與遠端一致，直接沿用既有 SHA
            tree_items.append({
                "path": rel_path,
                "mode": "100644",
                "type": "blob",
                "sha": local_sha
            })

    # 若需要上傳的檔案過多，進行全域上限保護 (以實際需要建立 Blob 上傳的檔案數為準，上限 500 檔)
    if len(pending_uploads) > 500:
        return {
            "status": "error",
            "output": f"檢測到待上傳變更檔案過多 ({len(pending_uploads)} 檔)，請先精簡目錄或檢查 .gitignore 排除不必要的檔案",
            "exit_code": -1
        }

    # 3. 使用 Semaphore 控制併發度 (10)，並透過 ThreadPool 非同步呼叫，不阻塞 Event Loop
    semaphore = asyncio.Semaphore(10)

    async def _upload_blob(rel_path: str, payload: Dict[str, Any]):
        async with semaphore:
            blob_res = await _github_api_request_async("POST", f"{api_base}/git/blobs", headers, payload)
            if blob_res.get("error"):
                raise RuntimeError(f"上傳 Blob 失敗 ({rel_path}): {blob_res.get('raw')}")
            return {"path": rel_path, "mode": "100644", "type": "blob", "sha": blob_res["data"]["sha"]}

    if pending_uploads:
        try:
            upload_tasks = [_upload_blob(rel_path, payload) for rel_path, payload in pending_uploads]
            uploaded_items = await asyncio.wait_for(asyncio.gather(*upload_tasks), timeout=60)
            tree_items.extend(uploaded_items)
        except asyncio.TimeoutError:
            return {"status": "error", "output": "Blob 上傳作業逾時 (超過 60 秒)", "exit_code": -1}
        except Exception as e:
            return {"status": "error", "output": str(e), "exit_code": -1}

    # 4. 若無任何變更，及早返回
    if not pending_uploads:
        return {"status": "success", "output": "工作區檔案與遠端一致，無須額外推送提交", "exit_code": 0}

    tree_payload = {"base_tree": base_tree_sha, "tree": tree_items}
    new_tree_res = await _github_api_request_async("POST", f"{api_base}/git/trees", headers, tree_payload)
    if new_tree_res.get("error"):
        return {"status": "error", "output": f"建立 Tree 失敗: {new_tree_res.get('raw')}", "exit_code": -1}
    new_tree_sha = new_tree_res["data"]["sha"]

    commit_payload = {
        "message": message,
        "tree": new_tree_sha,
        "parents": [parent_commit_sha]
    }
    new_commit_res = await _github_api_request_async("POST", f"{api_base}/git/commits", headers, commit_payload)
    if new_commit_res.get("error"):
        return {"status": "error", "output": f"建立 Commit 失敗: {new_commit_res.get('raw')}", "exit_code": -1}
    new_commit_sha = new_commit_res["data"]["sha"]

    update_payload = {"sha": new_commit_sha, "force": False}
    update_ref_res = await _github_api_request_async("PATCH", f"{api_base}/git/refs/heads/{branch}", headers, update_payload)
    if update_ref_res.get("error"):
        return {"status": "error", "output": f"更新分支指標失敗: {update_ref_res.get('raw')}", "exit_code": -1}

    return {"status": "success", "output": f"成功推送至 {repo} 的 {branch} 分支 (共推送 {len(pending_uploads)} 個變更檔案)，Commit SHA: {new_commit_sha}", "exit_code": 0}

async def handle_github_action(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    action = action.lower()
    if action in {"push", "push_workspace"}:
        return await push_workspace_to_github(
            repo=params.get("repo", ""),
            branch=params.get("branch", "main"),
            message=params.get("message", "Update from LLM Bridge"),
            subfolder=params.get("subfolder", "")
        )
    elif action == "pull":
        return git_pull(
            subfolder=params.get("subfolder", ""),
            remote=params.get("remote", "origin"),
            branch=params.get("branch", "main"),
            force_reset=params.get("force_reset", False)
        )
    elif action == "fetch":
        return git_fetch(
            subfolder=params.get("subfolder", ""),
            remote=params.get("remote", "origin")
        )
    elif action == "clone":
        return git_clone(
            repo_url=params.get("repo_url", ""),
            target_subfolder=params.get("target_subfolder", "")
        )
    elif action == "status":
        return git_status(
            subfolder=params.get("subfolder", "")
        )
    elif action == "log":
        return git_log(
            subfolder=params.get("subfolder", ""),
            max_count=params.get("max_count", 10),
            oneline=params.get("oneline", True),
            file_path=params.get("file_path", "")
        )
    elif action == "blame":
        return git_blame(
            file_path=params.get("file_path", ""),
            start_line=params.get("start_line"),
            end_line=params.get("end_line"),
            subfolder=params.get("subfolder", "")
        )
    elif action == "branch":
        return git_branch(
            action=params.get("action", "list"),
            branch_name=params.get("branch_name", ""),
            subfolder=params.get("subfolder", "")
        )
    elif action == "checkout":
        return git_checkout(
            branch_name=params.get("branch_name", ""),
            create_branch=params.get("create_branch", False),
            file_path=params.get("file_path", ""),
            subfolder=params.get("subfolder", "")
        )
    elif action == "clean":
        return git_clean(
            subfolder=params.get("subfolder", ""),
            dry_run=params.get("dry_run", False)
        )
    elif action == "list_actions":
        return list_available_actions()
    else:
        return {"status": "error", "output": f"不支援的 GitHub action: {action}", "exit_code": -1}
