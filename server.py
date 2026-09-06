import uvicorn
import subprocess
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List, Union
import executor
import github_client
import memory_manager
from config import SESSION_TOKEN, ALLOWED_ORIGINS
from github_client import git_clone, git_fetch, git_pull
from tools import TOOL_CATALOG, SUPPORTED_TOOLS, TOOL_HANDLERS, register_tool

app = FastAPI(title="LLM Local Bridge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ExecuteRequest(BaseModel):
    tool: str
    parameters: Optional[Dict[str, Any]] = {}

def check_docker_status() -> Dict[str, Any]:
    """檢查宿主機 Docker 守護程式是否正常運行"""
    try:
        res = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        if res.returncode == 0:
            return {"available": True, "message": "Docker 運行中"}
        else:
            return {"available": False, "message": f"Docker 未啟動或無回應: {res.stderr.strip()}"}
    except FileNotFoundError:
        return {"available": False, "message": "系統未偵測到 Docker 指令，請確認是否安裝並加入 PATH"}
    except Exception as e:
        return {"available": False, "message": f"Docker 檢查異常: {str(e)}"}

async def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="[Bridge] 缺少或無效的 Authorization 標頭")
    token = authorization.split(" ")[1]
    if token != SESSION_TOKEN:
        raise HTTPException(status_code=403, detail="[Bridge] Session Token 不正確")
    return token

@app.get("/health")
async def health_check():
    docker_status = check_docker_status()
    return {
        "status": "ok",
        "message": "[Bridge] 伺服器運行正常",
        "docker": docker_status
    }

@app.get("/context")
async def get_context(token: str = Depends(verify_token)):
    snapshot = memory_manager.capture_snapshot()
    prompt_text = memory_manager.get_latest_context_prompt()
    return {
        "status": "success",
        "snapshot": snapshot,
        "context_prompt": prompt_text
    }



@register_tool("execute_command")
async def _handle_execute_command(params: Dict[str, Any]):
    cmd = params.get("command", "").strip()
    if cmd.startswith("git ") or cmd == "git":
        return {
            "status": "error",
            "output": "[Bridge 格式防護] 禁止透過 execute_command 執行 git 指令。請改用專屬的 git 工具 (如 git_status, git_diff, git_log, git_blame, git_branch, git_clean, git_pull, git_push, git_clone) 以確保工作區安全性。",
            "exit_code": -1
        }
    timeout = params.get("timeout", 30)
    return await executor.run_shell_command(cmd, timeout=timeout)

@register_tool("run_script")
async def _handle_run_script(params: Dict[str, Any]):
    code = params.get("code", "")
    language = params.get("language", "python")
    timeout = params.get("timeout", 30)
    return await executor.run_transient_script(code=code, language=language, timeout=timeout)

@register_tool("file_write")
async def _handle_file_write(params: Dict[str, Any]):
    path = params.get("path", "")
    content = params.get("content", "")
    return executor.write_workspace_file(path, content)

@register_tool("file_replace")
async def _handle_file_replace(params: Dict[str, Any]):
    path = params.get("path", "")
    target = params.get("target", "")
    replacement = params.get("replacement", "")
    return executor.replace_file_content(path, target, replacement)

@register_tool("patch_and_test")
async def _handle_patch_and_test(params: Dict[str, Any]):
    path = params.get("path", "")
    target = params.get("target", "")
    replacement = params.get("replacement", "")
    test_cmd = params.get("test_command", "")
    timeout = params.get("timeout", 30)
    auto_rollback = params.get("auto_rollback", False)
    return await executor.patch_and_test_file(path, target, replacement, test_cmd, timeout=timeout, auto_rollback=auto_rollback)

@register_tool("file_read")
async def _handle_file_read(params: Dict[str, Any]):
    path = params.get("path", "")
    start_line = params.get("start_line")
    end_line = params.get("end_line")
    return executor.read_workspace_file(path, start_line=start_line, end_line=end_line)

@register_tool("git_diff")
async def _handle_git_diff(params: Dict[str, Any]):
    path = params.get("path", "")
    return executor.get_workspace_git_diff(path)

@register_tool("git_status")
async def _handle_git_status(params: Dict[str, Any]):
    return await github_client.handle_github_action("status", params)

@register_tool("git_log")
async def _handle_git_log(params: Dict[str, Any]):
    return await github_client.handle_github_action("log", params)

@register_tool("git_blame")
async def _handle_git_blame(params: Dict[str, Any]):
    return await github_client.handle_github_action("blame", params)

@register_tool("git_branch")
async def _handle_git_branch(params: Dict[str, Any]):
    return await github_client.handle_github_action("branch", params)

@register_tool("git_checkout")
async def _handle_git_checkout(params: Dict[str, Any]):
    return await github_client.handle_github_action("checkout", params)

@register_tool("git_clean")
async def _handle_git_clean(params: Dict[str, Any]):
    return await github_client.handle_github_action("clean", params)

@register_tool("list_dir")
async def _handle_list_dir(params: Dict[str, Any]):
    path = params.get("path", "")
    max_depth = params.get("max_depth", 3)
    return executor.list_workspace_dir(path, max_depth=max_depth)

@register_tool("get_outline")
async def _handle_get_outline(params: Dict[str, Any]):
    path = params.get("path", "")
    return executor.get_file_outline(path)

@register_tool("search_codebase")
async def _handle_search_codebase(params: Dict[str, Any]):
    query = params.get("query", "")
    path = params.get("path", "")
    include_pattern = params.get("include_pattern", "")
    max_results = int(params.get("max_results", 50))
    return executor.search_codebase(query, path=path, include_pattern=include_pattern, max_results=max_results)

@register_tool("find_references")
async def _handle_find_references(params: Dict[str, Any]):
    symbol = params.get("symbol", "")
    file_type = params.get("file_type", "")
    scope_dir = params.get("scope_dir", "")
    return executor.find_references(symbol, file_type=file_type, scope_dir=scope_dir)

@register_tool("git_clone")
async def _handle_git_clone(params: Dict[str, Any]):
    return await github_client.handle_github_action("clone", params)

@register_tool("git_pull")
async def _handle_git_pull(params: Dict[str, Any]):
    return await github_client.handle_github_action("pull", params)

@register_tool("git_push")
async def _handle_git_push(params: Dict[str, Any]):
    return await github_client.handle_github_action("push", params)

@register_tool("capture_memory")
async def _handle_capture_memory(params: Dict[str, Any]):
    snapshot = memory_manager.capture_snapshot()
    return {"status": "success", "output": "專案架構快照已更新", "snapshot": snapshot}

@register_tool("list_tool")
async def _handle_list_tool(params: Dict[str, Any]):
    category = params.get("category", "").strip().lower()
    if category:
        matched_tools = TOOL_CATALOG.get(category, [])
        return {
            "status": "success",
            "category": category,
            "total_tools": len(matched_tools),
            "tools": matched_tools,
            "exit_code": 0
        }
    return {
        "status": "success",
        "total_tools": len(SUPPORTED_TOOLS),
        "tools": TOOL_CATALOG,
        "exit_code": 0
    }

import inspect

async def _execute_single_tool(tool_name: str, params: Dict[str, Any]) -> dict:
    handler = TOOL_HANDLERS.get(tool_name)
    if handler:
        if inspect.iscoroutinefunction(handler):
            return await handler(params)
        return handler(params)

    import difflib
    matches = difflib.get_close_matches(tool_name, SUPPORTED_TOOLS, n=3, cutoff=0.4)
    suggestion = f"。您是否是指: {', '.join(matches)}？" if matches else ""
    available_list = ", ".join(SUPPORTED_TOOLS)
    return {
        "status": "error",
        "output": f"[Bridge] 未知的工具名稱: '{tool_name}'{suggestion}\n可用工具清單: [{available_list}]",
        "exit_code": -1
    }

@app.post("/execute")
async def execute_tool(req: Union[ExecuteRequest, List[ExecuteRequest]], token: str = Depends(verify_token)):
    try:
        # 支援單一指令請求
        if isinstance(req, ExecuteRequest):
            tool_name = req.tool
            params = req.parameters or {}
            print(f"[Bridge] 收到單一執行請求: {tool_name}")
            res = await _execute_single_tool(tool_name, params)
            if tool_name in ["file_write", "file_replace", "patch_and_test", "run_script"]:
                memory_manager.capture_snapshot()
            return res

        # 支援批次陣列請求 (Fail-Fast pipeline)
        if isinstance(req, list):
            print(f"[Bridge] 收到批次指令請求，共 {len(req)} 項")
            batch_results = []
            has_file_modifications = False
            for idx, item in enumerate(req):
                tool_name = item.tool
                params = item.parameters or {}
                if tool_name in ["file_write", "file_replace", "patch_and_test", "run_script"]:
                    has_file_modifications = True
                print(f"[Bridge] 執行批次步驟 [{idx + 1}/{len(req)}]: {tool_name}")
                res = await _execute_single_tool(tool_name, params)
                batch_results.append({
                    "step": idx + 1,
                    "tool": tool_name,
                    "result": res
                })

                # Fail-Fast 中斷檢查
                status = res.get("status")
                exit_code = res.get("exit_code", 0)
                if status not in ["success", "ok"] or exit_code != 0:
                    print(f"[Bridge] 批次步驟 [{idx + 1}] 失敗，中斷後續執行。")
                    if has_file_modifications:
                        memory_manager.capture_snapshot()
                    return {
                        "status": "failed",
                        "interrupted_at": idx + 1,
                        "total_steps": len(req),
                        "batch_results": batch_results,
                        "output": f"第 {idx + 1} 步執行失敗 ({tool_name})，已中止後續指令。",
                        "exit_code": exit_code if exit_code != 0 else -1
                    }

            if has_file_modifications:
                memory_manager.capture_snapshot()

            return {
                "status": "success",
                "total_steps": len(req),
                "batch_results": batch_results,
                "output": f"全部 {len(req)} 項批次指令順利執行完成。",
                "exit_code": 0
            }

    except Exception as e:
        print(f"[Bridge] 執行錯誤: {e}")
        return {"status": "error", "output": f"[Bridge] 伺服器內部錯誤: {str(e)}", "exit_code": -1}

class GitCloneRequest(BaseModel):
    repo_url: str
    target_subfolder: str = ""

class GitSyncRequest(BaseModel):
    subfolder: str = ""
    remote: str = "origin"
    branch: str = "main"
    force_reset: bool = False

@app.post("/git/clone")
async def handle_git_clone(req: GitCloneRequest, authorized: bool = Depends(verify_token)):
    return git_clone(req.repo_url, req.target_subfolder)

@app.post("/git/fetch")
async def handle_git_fetch(req: GitSyncRequest, authorized: bool = Depends(verify_token)):
    return git_fetch(req.subfolder, req.remote)

@app.post("/git/pull")
async def handle_git_pull(req: GitSyncRequest, authorized: bool = Depends(verify_token)):
    return git_pull(req.subfolder, req.remote, req.branch, req.force_reset)

if __name__ == "__main__":
    print(f"[Bridge] 🚀 Server 啟動於 127.0.0.1:8000 (Token: {SESSION_TOKEN})")
    docker_check = check_docker_status()
    if docker_check["available"]:
        print(f"[Bridge] 🐳 Docker 狀態: {docker_check['message']}")
    else:
        print(f"[Bridge] ⚠️ Docker 狀態警告: {docker_check['message']}")
    memory_manager.capture_snapshot()
    uvicorn.run(app, host="127.0.0.1", port=8000)
