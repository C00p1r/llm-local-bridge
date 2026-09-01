import sys
import os
import re
import difflib
from pathlib import Path
from typing import Dict, Any, Tuple
import httpx
import base64
from config import GITHUB_TOKEN, WORKSPACE_DIR

GITHUB_API_BASE = 'https://api.github.com'
IGNORE_NAMES = {'.git', '.env', '__pycache__', 'node_modules', '.venv', 'venv', '.idea', '.vscode', '.bridge_memory.json'}

def get_headers() -> Dict[str, str]:
    if not GITHUB_TOKEN:
        raise ValueError('[GitHub Client] 未設定 GITHUB_TOKEN，請於 .env 填入 Personal Access Token')
    return {
        'Authorization': f'Bearer {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
    }

async def get_authenticated_user() -> str:
    headers = get_headers()
    async with httpx.AsyncClient() as client:
        res = await client.get(f'{GITHUB_API_BASE}/user', headers=headers)
        if res.status_code != 200:
            raise RuntimeError(f'[GitHub] 無法取得使用者資訊 (Status {res.status_code}): {res.text}')
        return res.json()['login']

def resolve_repo_full_name(repo: str, username: str) -> str:
    return repo if '/' in repo else f'{username}/{repo}'

async def ensure_repo_exists(owner: str, repo_name: str, private: bool = False):
    headers = get_headers()
    async with httpx.AsyncClient() as client:
        res = await client.get(f'{GITHUB_API_BASE}/repos/{owner}/{repo_name}', headers=headers)
        if res.status_code == 404:
            create_res = await client.post(
                f'{GITHUB_API_BASE}/user/repos',
                headers=headers,
                json={'name': repo_name, 'private': private, 'auto_init': True}
            )
            if create_res.status_code not in (200, 201):
                raise RuntimeError(f'[GitHub] 建立 Repository 失敗: {create_res.text}')
        elif res.status_code != 200:
            raise RuntimeError(f'[GitHub] 查詢 Repository 失敗: {res.text}')

async def get_remote_file_content(repo: str, file_path: str, branch: str = 'main') -> Dict[str, Any]:
    username = await get_authenticated_user()
    full_repo = resolve_repo_full_name(repo, username)
    headers = get_headers()
    clean_file_path = Path(file_path).as_posix()
    async with httpx.AsyncClient() as client:
        res = await client.get(f'{GITHUB_API_BASE}/repos/{full_repo}/contents/{clean_file_path}', headers=headers, params={'ref': branch})
        if res.status_code == 404:
            return {'status': 'not_found', 'output': '遠端無此檔案', 'sha': None}
        if res.status_code != 200:
            raise RuntimeError(f'[GitHub] 讀取遠端檔案失敗: {res.text}')
        data = res.json()
        if 'content' in data and data.get('encoding') == 'base64':
            decoded_content = base64.b64decode(data['content']).decode('utf-8', errors='replace')
            return {'status': 'success', 'output': decoded_content, 'sha': data.get('sha')}
        return {'status': 'error', 'output': '無法解析檔案內容', 'raw': data}

async def get_file_diff(repo: str, file_path: str, branch: str = 'main') -> Dict[str, Any]:
    username = await get_authenticated_user()
    full_repo = resolve_repo_full_name(repo, username)
    normalized_path = Path(file_path).as_posix()
    local_file = (WORKSPACE_DIR / normalized_path).resolve()
    
    local_exists = local_file.exists() and local_file.is_file()
    local_content = local_file.read_text(encoding='utf-8', errors='replace') if local_exists else None

    remote_res = await get_remote_file_content(full_repo, normalized_path, branch=branch)
    remote_exists = remote_res.get('status') == 'success'
    remote_content = remote_res.get('output') if remote_exists else None

    if not local_exists and not remote_exists:
        return {'status': 'error', 'output': f'本機與遠端均無檔案: {normalized_path}'}

    if not local_exists and remote_exists:
        return {
            'status': 'success',
            'state': 'deleted_locally',
            'output': f'[Status] 檔案已於本機刪除，但仍存在於遠端 ({full_repo}:{branch})'
        }
    if local_exists and not remote_exists:
        return {
            'status': 'success',
            'state': 'new_file',
            'output': f'[Status] 本機全新檔案 (遠端不存在): {normalized_path}'
        }

    # 進行文字 diff 比對
    remote_lines = remote_content.splitlines(keepends=True)
    local_lines = local_content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(remote_lines, local_lines, fromfile=f'remote/{normalized_path}', tofile=f'local/{normalized_path}'))

    if not diff:
        return {'status': 'success', 'state': 'identical', 'output': '本機與遠端內容一致，無差異'}

    return {
        'status': 'success',
        'state': 'modified',
        'output': ''.join(diff)
    }

async def commit_single_file(repo: str, file_path: str, commit_message: str, branch: str = 'main') -> Dict[str, Any]:
    username = await get_authenticated_user()
    full_repo = resolve_repo_full_name(repo, username)
    headers = get_headers()
    clean_file_path = Path(file_path).as_posix()
    local_file = (WORKSPACE_DIR / clean_file_path).resolve()
    if not local_file.exists() or not local_file.is_file():
        raise FileNotFoundError(f'本機找不到目標檔案: {clean_file_path}')
    content_bytes = local_file.read_bytes()
    content_b64 = base64.b64encode(content_bytes).decode('utf-8')
    async with httpx.AsyncClient() as client:
        remote_url = f'{GITHUB_API_BASE}/repos/{full_repo}/contents/{clean_file_path}'
        res = await client.get(remote_url, headers=headers, params={'ref': branch})
        payload = {'message': commit_message, 'content': content_b64, 'branch': branch}
        if res.status_code == 200:
            payload['sha'] = res.json()['sha']
        put_res = await client.put(remote_url, headers=headers, json=payload)
        if put_res.status_code not in (200, 201):
            raise RuntimeError(f'[GitHub] 單檔 Commit 失敗: {put_res.text}')
        return {'status': 'success', 'output': f'成功提交檔案 {clean_file_path} 至 {full_repo}:{branch}', 'commit': put_res.json()}

async def push_workspace_to_repo(repo: str, branch: str = 'main', message: str = 'Update workspace via LLM Bridge', subfolder: str = '') -> Dict[str, Any]:
    username = await get_authenticated_user()
    repo_name = repo.split('/')[-1] if '/' in repo else repo
    full_repo = f'{username}/{repo_name}'
    await ensure_repo_exists(username, repo_name)
    headers = get_headers()
    clean_subfolder = Path(subfolder).as_posix() if subfolder else ''
    async with httpx.AsyncClient() as client:
        ref_res = await client.get(f'{GITHUB_API_BASE}/repos/{full_repo}/git/ref/heads/{branch}', headers=headers)
        parent_commit_sha = ref_res.json()['object']['sha'] if ref_res.status_code == 200 else None
        target_dir = (WORKSPACE_DIR / clean_subfolder).resolve() if clean_subfolder else WORKSPACE_DIR
        tree_items = []
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if d not in IGNORE_NAMES]
            for f in files:
                if f in IGNORE_NAMES or f.startswith('.env'):
                    continue
                full_path = Path(root) / f
                rel_path = full_path.relative_to(target_dir).as_posix()
                content = full_path.read_text(encoding='utf-8', errors='replace')
                blob_res = await client.post(
                    f'{GITHUB_API_BASE}/repos/{full_repo}/git/blobs',
                    headers=headers,
                    json={'content': content, 'encoding': 'utf-8'}
                )
                if blob_res.status_code != 201:
                    raise RuntimeError(f'[GitHub] 建立 Blob 失敗 ({rel_path}): {blob_res.text}')
                tree_items.append({'path': rel_path, 'mode': '100644', 'type': 'blob', 'sha': blob_res.json()['sha']})
        if not tree_items:
            return {'status': 'success', 'output': '工作區為空或無新變更，未進行 Commit'}
        tree_payload = {'tree': tree_items}
        if parent_commit_sha:
            tree_payload['base_tree'] = parent_commit_sha
        tree_res = await client.post(f'{GITHUB_API_BASE}/repos/{full_repo}/git/trees', headers=headers, json=tree_payload)
        if tree_res.status_code != 201:
            raise RuntimeError(f'[GitHub] 建立 Tree 失敗: {tree_res.text}')
        new_tree_sha = tree_res.json()['sha']
        commit_payload = {'message': message, 'tree': new_tree_sha}
        if parent_commit_sha:
            commit_payload['parents'] = [parent_commit_sha]
        commit_res = await client.post(f'{GITHUB_API_BASE}/repos/{full_repo}/git/commits', headers=headers, json=commit_payload)
        if commit_res.status_code != 201:
            raise RuntimeError(f'[GitHub] 建立 Commit 失敗: {commit_res.text}')
        new_commit_sha = commit_res.json()['sha']
        if parent_commit_sha:
            update_ref_res = await client.patch(f'{GITHUB_API_BASE}/repos/{full_repo}/git/refs/heads/{branch}', headers=headers, json={'sha': new_commit_sha, 'force': True})
        else:
            update_ref_res = await client.post(f'{GITHUB_API_BASE}/repos/{full_repo}/git/refs', headers=headers, json={'ref': f'refs/heads/{branch}', 'sha': new_commit_sha})
        if update_ref_res.status_code not in (200, 201):
            raise RuntimeError(f'[GitHub] 更新 Branch Reference 失敗: {update_ref_res.text}')
        return {'status': 'success', 'output': f'成功推送至 {full_repo}:{branch}', 'commit_sha': new_commit_sha}

async def handle_github_action(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if action == 'push_workspace':
            return await push_workspace_to_repo(
                repo=params.get('repo', ''),
                branch=params.get('branch', 'main'),
                message=params.get('message', 'Update from Local Bridge'),
                subfolder=params.get('subfolder', '')
            )
        elif action == 'commit_file':
            return await commit_single_file(
                repo=params.get('repo', ''),
                file_path=params.get('file_path', ''),
                commit_message=params.get('message', 'Update file via LLM Bridge'),
                branch=params.get('branch', 'main')
            )
        elif action == 'get_remote_file':
            return await get_remote_file_content(
                repo=params.get('repo', ''),
                file_path=params.get('file_path', ''),
                branch=params.get('branch', 'main')
            )
        elif action == 'diff_file':
            return await get_file_diff(
                repo=params.get('repo', ''),
                file_path=params.get('file_path', ''),
                branch=params.get('branch', 'main')
            )
        else:
            return {'status': 'error', 'output': f'未知的 GitHub Action: {action}'}
    except Exception as e:
        return {'status': 'error', 'output': f'[GitHub Client] 操作失敗: {str(e)}'}
