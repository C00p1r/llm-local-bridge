import base64
import json
import os
from pathlib import Path
from typing import Dict, Any, List
import urllib.request
import urllib.error
from config import GITHUB_TOKEN, WORKSPACE_DIR

GITHUB_API_BASE = "https://api.github.com"

def _make_request(url: str, method: str = "GET", data: Dict[str, Any] = None) -> Dict[str, Any]:
    if not GITHUB_TOKEN:
        return {"status": "error", "output": "未設定 GITHUB_TOKEN，請於 .env 或環境變數中設定", "exit_code": -1}

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "LLM-Local-Bridge-Agent"
    }
    payload = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode("utf-8")
            return {"status": "success", "output": res_body, "exit_code": 0}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return {"status": "error", "output": f"HTTP {e.code}: {err_body}", "exit_code": e.code}
    except Exception as e:
        return {"status": "error", "output": str(e), "exit_code": -1}

async def push_workspace_to_repo(repo_name: str, branch: str = "main", commit_message: str = "Initial commit via LLM Local Bridge", private: bool = False, subfolder: str = "") -> Dict[str, Any]:
    target_dir = (WORKSPACE_DIR / subfolder).resolve() if subfolder else WORKSPACE_DIR.resolve()
    if not target_dir.exists():
        return {"status": "error", "output": f"目錄不存在: {target_dir}", "exit_code": -1}

    user_res = _make_request(f"{GITHUB_API_BASE}/user")
    if user_res["status"] != "success":
        return user_res
    username = json.loads(user_res["output"])["login"]

    full_repo = f"{username}/{repo_name}" if "/" not in repo_name else repo_name
    owner, rname = full_repo.split("/", 1)

    # 1. 檢查或建立 Repository
    repo_res = _make_request(f"{GITHUB_API_BASE}/repos/{owner}/{rname}")
    if repo_res["status"] != "success":
        print(f"[Bridge] 建立新的 GitHub 倉庫: {full_repo}")
        create_res = _make_request(f"{GITHUB_API_BASE}/user/repos", method="POST", data={
            "name": rname,
            "private": private,
            "auto_init": True
        })
        if create_res["status"] != "success":
            return create_res

    # 2. 收集目錄下所有檔案並上傳 Blob
    tree_items = []
    exclude_patterns = {".git", "__pycache__", ".venv", "node_modules", ".env"}
    
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in exclude_patterns]
        for f in files:
            if f in exclude_patterns or f.endswith(".pyc"):
                continue
            filepath = Path(root) / f
            rel_path = filepath.relative_to(target_dir).as_posix()
            
            try:
                content_bytes = filepath.read_bytes()
                content_b64 = base64.b64encode(content_bytes).decode("utf-8")
                
                blob_res = _make_request(
                    f"{GITHUB_API_BASE}/repos/{owner}/{rname}/git/blobs",
                    method="POST",
                    data={"content": content_b64, "encoding": "base64"}
                )
                if blob_res["status"] != "success":
                    return blob_res
                
                blob_sha = json.loads(blob_res["output"])["sha"]
                tree_items.append({
                    "path": rel_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha
                })
            except Exception as e:
                print(f"[Bridge] 讀取檔案失敗: {rel_path}, 錯誤: {e}")

    if not tree_items:
        return {"status": "error", "output": "沒有可上傳的檔案", "exit_code": -1}

    # 3. 建立 Tree
    tree_res = _make_request(
        f"{GITHUB_API_BASE}/repos/{owner}/{rname}/git/trees",
        method="POST",
        data={"tree": tree_items}
    )
    if tree_res["status"] != "success":
        return tree_res
    tree_sha = json.loads(tree_res["output"])["sha"]

    # 4. 取得最新 Commit SHA（若存在）
    parent_commits = []
    ref_res = _make_request(f"{GITHUB_API_BASE}/repos/{owner}/{rname}/git/ref/heads/{branch}")
    if ref_res["status"] == "success":
        latest_commit_sha = json.loads(ref_res["output"])["object"]["sha"]
        parent_commits.append(latest_commit_sha)

    # 5. 建立 Commit
    commit_data = {
        "message": commit_message,
        "tree": tree_sha,
        "parents": parent_commits
    }
    commit_res = _make_request(
        f"{GITHUB_API_BASE}/repos/{owner}/{rname}/git/commits",
        method="POST",
        data=commit_data
    )
    if commit_res["status"] != "success":
        return commit_res
    new_commit_sha = json.loads(commit_res["output"])["sha"]

    # 6. 更新或建立 Branch Ref
    if parent_commits:
        update_ref = _make_request(
            f"{GITHUB_API_BASE}/repos/{owner}/{rname}/git/refs/heads/{branch}",
            method="PATCH",
            data={"sha": new_commit_sha, "force": True}
        )
        return update_ref
    else:
        create_ref = _make_request(
            f"{GITHUB_API_BASE}/repos/{owner}/{rname}/git/refs",
            method="POST",
            data={"ref": f"refs/heads/{branch}", "sha": new_commit_sha}
        )
        return create_ref

async def handle_github_action(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if action == "get_repo":
        repo = params.get("repo", "")
        return _make_request(f"{GITHUB_API_BASE}/repos/{repo}")
    elif action == "list_issues":
        repo = params.get("repo", "")
        return _make_request(f"{GITHUB_API_BASE}/repos/{repo}/issues")
    elif action == "create_issue":
        repo = params.get("repo", "")
        return _make_request(f"{GITHUB_API_BASE}/repos/{repo}/issues", method="POST", data=params)
    elif action == "create_pull_request":
        repo = params.get("repo", "")
        return _make_request(f"{GITHUB_API_BASE}/repos/{repo}/pulls", method="POST", data=params)
    elif action == "get_file":
        repo = params.get("repo", "")
        path = params.get("path", "")
        return _make_request(f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}")
    elif action == "push_workspace":
        repo = params.get("repo", "")
        branch = params.get("branch", "main")
        message = params.get("message", "Update via LLM Local Bridge")
        private = params.get("private", False)
        subfolder = params.get("subfolder", "")
        return await push_workspace_to_repo(repo, branch=branch, commit_message=message, private=private, subfolder=subfolder)
    return {"status": "error", "output": f"不支援的 GitHub action: {action}", "exit_code": -1}
