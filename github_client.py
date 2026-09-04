import os
import shutil
import subprocess
import json
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
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
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
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, timeout=30)
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
            res = subprocess.run(reset_cmd, cwd=str(target_path), capture_output=True, text=True, timeout=30)
            if res.returncode == 0:
                return {"status": "success", "output": f"已強制重設至 {remote}/{branch}", "exit_code": 0}
            else:
                return {"status": "failed", "output": res.stderr, "exit_code": res.returncode}
        else:
            pull_cmd = [git_bin, "pull", remote, branch]
            res = subprocess.run(pull_cmd, cwd=str(target_path), capture_output=True, text=True, timeout=30)
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
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, timeout=15)
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
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, timeout=20)
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
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, timeout=20)
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
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, timeout=20)
        if res.returncode == 0:
            output = res.stdout.strip() or res.stderr.strip() or f"成功執行 branch {action}"
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
        res = subprocess.run(cmd, cwd=str(target_path), capture_output=True, text=True, timeout=20)
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

async def push_workspace_to_github(repo: str, branch: str = "main", message: str = "Update from LLM Bridge", subfolder: str = "") -> Dict[str, Any]:
    if not GITHUB_TOKEN:
        return {"status": "error", "output": "未設定 GITHUB_TOKEN，無法使用 GitHub API 進行推送", "exit_code": -1}
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "LLM-Local-Bridge-Client"
    }
    api_base = f"https://api.github.com/repos/{repo}"

    ref_res = _github_api_request("GET", f"{api_base}/git/ref/heads/{branch}", headers)
    if ref_res.get("error"):
        return {"status": "error", "output": f"獲取分支 {branch} 失敗: {ref_res.get('raw')}", "exit_code": -1}
    parent_commit_sha = ref_res["data"]["object"]["sha"]

    commit_res = _github_api_request("GET", f"{api_base}/git/commits/{parent_commit_sha}", headers)
    if commit_res.get("error"):
        return {"status": "error", "output": f"獲取 Commit {parent_commit_sha} 失敗: {commit_res.get('raw')}", "exit_code": -1}
    base_tree_sha = commit_res["data"]["tree"]["sha"]

    target_path = _resolve_target_path(subfolder)
    tree_items = []
    ignored_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "target", "dist"}

    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for f in files:
            file_full = Path(root) / f
            try:
                content_bytes = file_full.read_bytes()
                blob_payload = {"content": content_bytes.decode("utf-8"), "encoding": "utf-8"}
            except UnicodeDecodeError:
                import base64
                blob_payload = {"content": base64.b64encode(content_bytes).decode("utf-8"), "encoding": "base64"}
            except Exception:
                continue

            blob_res = _github_api_request("POST", f"{api_base}/git/blobs", headers, blob_payload)
            if blob_res.get("error"):
                return {"status": "error", "output": f"上傳 Blob 失敗 ({f}): {blob_res.get('raw')}", "exit_code": -1}
            
            rel_path = str(file_full.relative_to(target_path)).replace("\\", "/")
            tree_items.append({
                "path": rel_path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_res["data"]["sha"]
            })

    if not tree_items:
        return {"status": "error", "output": "沒有發現可推送的檔案", "exit_code": -1}

    tree_payload = {"base_tree": base_tree_sha, "tree": tree_items}
    new_tree_res = _github_api_request("POST", f"{api_base}/git/trees", headers, tree_payload)
    if new_tree_res.get("error"):
        return {"status": "error", "output": f"建立 Tree 失敗: {new_tree_res.get('raw')}", "exit_code": -1}
    new_tree_sha = new_tree_res["data"]["sha"]

    commit_payload = {
        "message": message,
        "tree": new_tree_sha,
        "parents": [parent_commit_sha]
    }
    new_commit_res = _github_api_request("POST", f"{api_base}/git/commits", headers, commit_payload)
    if new_commit_res.get("error"):
        return {"status": "error", "output": f"建立 Commit 失敗: {new_commit_res.get('raw')}", "exit_code": -1}
    new_commit_sha = new_commit_res["data"]["sha"]

    update_payload = {"sha": new_commit_sha, "force": False}
    update_ref_res = _github_api_request("PATCH", f"{api_base}/git/refs/heads/{branch}", headers, update_payload)
    if update_ref_res.get("error"):
        return {"status": "error", "output": f"更新分支指標失敗: {update_ref_res.get('raw')}", "exit_code": -1}

    return {"status": "success", "output": f"成功推送至 {repo} 的 {branch} 分支，Commit SHA: {new_commit_sha}", "exit_code": 0}

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
    elif action == "clean":
        return git_clean(
            subfolder=params.get("subfolder", ""),
            dry_run=params.get("dry_run", False)
        )
    elif action == "list_actions":
        return list_available_actions()
    else:
        return {"status": "error", "output": f"不支援的 GitHub action: {action}", "exit_code": -1}
