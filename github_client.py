import os
import shutil
import subprocess
from typing import Dict, Any, Optional
import httpx
from config import WORKSPACE_DIR, GITHUB_TOKEN

AVAILABLE_ACTIONS = {
    "pull": "Pull changes from remote repository (params: subfolder, remote, branch, force_reset)",
    "fetch": "Fetch refs from remote repository (params: subfolder, remote)",
    "clone": "Clone a repository into workspace (params: repo_url, target_subfolder)",
    "push": "Commit and push workspace/subfolder to GitHub via API (params: repo, branch, message, subfolder)",
    "push_workspace": "Alias for push (params: repo, branch, message, subfolder)",
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

def git_clone(repo_url: str, target_subfolder: str = "") -> Dict[str, Any]:
    try:
        git_bin = get_git_executable()
        target_path = (WORKSPACE_DIR / target_subfolder).resolve() if target_subfolder else WORKSPACE_DIR
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
        target_path = (WORKSPACE_DIR / subfolder).resolve() if subfolder else WORKSPACE_DIR
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
        target_path = (WORKSPACE_DIR / subfolder).resolve() if subfolder else WORKSPACE_DIR
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

async def push_workspace_to_github(repo: str, branch: str = "main", message: str = "Update from LLM Bridge", subfolder: str = "") -> Dict[str, Any]:
    if not GITHUB_TOKEN:
        return {"status": "error", "output": "未設定 GITHUB_TOKEN，無法使用 GitHub API 進行推送", "exit_code": -1}
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    base_url = f"https://api.github.com/repos/{repo}"
    target_dir = (WORKSPACE_DIR / subfolder).resolve() if subfolder else WORKSPACE_DIR
    if not target_dir.exists():
        return {"status": "error", "output": f"指定的 subfolder 不存在: {target_dir}", "exit_code": -1}

    async with httpx.AsyncClient(timeout=40.0) as client:
        ref_res = await client.get(f"{base_url}/git/refs/heads/{branch}", headers=headers)
        if ref_res.status_code != 200:
            return {"status": "error", "output": f"無法取得分支資訊: {ref_res.status_code} {ref_res.text}", "exit_code": ref_res.status_code}
        latest_commit_sha = ref_res.json()["object"]["sha"]
        commit_res = await client.get(f"{base_url}/git/commits/{latest_commit_sha}", headers=headers)
        if commit_res.status_code != 200:
            return {"status": "error", "output": f"無法取得 commit 資訊: {commit_res.status_code} {commit_res.text}", "exit_code": commit_res.status_code}
        base_tree_sha = commit_res.json()["tree"]["sha"]

        tree_items = []
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "node_modules", ".venv", "venv"}]
            for file in files:
                if file.startswith(".bridge_memory"):
                    continue
                full_path = Path(root) / file
                rel_path = full_path.relative_to(target_dir).as_posix()
                try:
                    content = full_path.read_text(encoding="utf-8")
                    tree_items.append({"path": rel_path, "mode": "100644", "type": "blob", "content": content})
                except Exception:
                    continue

        if not tree_items:
            return {"status": "error", "output": "沒有發現可推送的檔案", "exit_code": -1}

        tree_res = await client.post(f"{base_url}/git/trees", headers=headers, json={"base_tree": base_tree_sha, "tree": tree_items})
        if tree_res.status_code != 201:
            return {"status": "error", "output": f"建立 Tree 失敗: {tree_res.status_code} {tree_res.text}", "exit_code": tree_res.status_code}
        new_tree_sha = tree_res.json()["sha"]

        new_commit_res = await client.post(f"{base_url}/git/commits", headers=headers, json={"message": message, "tree": new_tree_sha, "parents": [latest_commit_sha]})
        if new_commit_res.status_code != 201:
            return {"status": "error", "output": f"建立 Commit 失敗: {new_commit_res.status_code} {new_commit_res.text}", "exit_code": new_commit_res.status_code}
        new_commit_sha = new_commit_res.json()["sha"]

        update_ref_res = await client.patch(f"{base_url}/git/refs/heads/{branch}", headers=headers, json={"sha": new_commit_sha, "force": False})
        if update_ref_res.status_code == 200:
            return {"status": "success", "output": update_ref_res.text, "exit_code": 0}
        else:
            return {"status": "error", "output": f"更新分支失敗: {update_ref_res.status_code} {update_ref_res.text}", "exit_code": update_ref_res.status_code}

async def handle_github_action(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if action in ["push", "push_workspace"]:
        repo = params.get("repo", "")
        branch = params.get("branch", "main")
        message = params.get("message", "Update from LLM Bridge")
        subfolder = params.get("subfolder", "")
        return await push_workspace_to_github(repo=repo, branch=branch, message=message, subfolder=subfolder)
    elif action == "pull":
        subfolder = params.get("subfolder", "")
        remote = params.get("remote", "origin")
        branch = params.get("branch", "main")
        force_reset = params.get("force_reset", False)
        return git_pull(subfolder, remote, branch, force_reset)
    elif action == "fetch":
        subfolder = params.get("subfolder", "")
        remote = params.get("remote", "origin")
        return git_fetch(subfolder, remote)
    elif action == "clone":
        repo_url = params.get("repo_url", "")
        target_subfolder = params.get("target_subfolder", "")
        return git_clone(repo_url, target_subfolder)
    elif action in ["list_actions", "list_available_actions"]:
        return list_available_actions()
    else:
        return {
            "status": "error",
            "output": f"未知的 GitHub Action: {action}。可使用 action: 'list_actions' 查詢支援清單。",
            "available_actions": list(AVAILABLE_ACTIONS.keys()),
            "exit_code": -1
        }
