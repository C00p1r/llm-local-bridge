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

SUPPORTED_TOOLS = [
    "execute_command",
    "run_script",
    "file_read",
    "file_write",
    "file_replace",
    "patch_and_test",
    "git_clone",
    "git_pull",
    "git_push",
    "git_diff",
    "git_status",
    "git_log",
    "git_blame",
    "git_branch",
    "git_checkout",
    "git_clean",
    "list_dir",
    "get_outline",
    "search_codebase",
    "find_references",
    "capture_memory",
    "list_tool"
]

async def _execute_single_tool(tool_name: str, params: Dict[str, Any]) -> dict:
    if tool_name == "execute_command":
        cmd = params.get("command", "").strip()
        # 攔截 Git 指令並給予精確提示
        if cmd.startswith("git ") or cmd == "git":
            return {
                "status": "error",
                "output": "[Bridge 格式防護] 禁止透過 execute_command 執行 git 指令。請改用專屬的 git 工具 (如 git_status, git_diff, git_log, git_blame, git_branch, git_clean, git_pull, git_push, git_clone) 以確保工作區安全性。",
                "exit_code": -1
            }
        timeout = params.get("timeout", 30)
        return await executor.run_shell_command(cmd, timeout=timeout)

    elif tool_name == "run_script":
        code = params.get("code", "")
        language = params.get("language", "python")
        timeout = params.get("timeout", 30)
        res = await executor.run_transient_script(code=code, language=language, timeout=timeout)
        memory_manager.capture_snapshot()
        return res

    elif tool_name == "file_write":
        path = params.get("path", "")
        content = params.get("content", "")
        res = executor.write_workspace_file(path, content)
        memory_manager.capture_snapshot()
        return res

    elif tool_name == "file_replace":
        path = params.get("path", "")
        target = params.get("target", "")
        replacement = params.get("replacement", "")
        res = executor.replace_file_content(path, target, replacement)
        memory_manager.capture_snapshot()
        return res

    elif tool_name == "patch_and_test":
        path = params.get("path", "")
        target = params.get("target", "")
        replacement = params.get("replacement", "")
        test_cmd = params.get("test_command", "")
        timeout = params.get("timeout", 30)
        auto_rollback = params.get("auto_rollback", False)
        res = await executor.patch_and_test_file(path, target, replacement, test_cmd, timeout=timeout, auto_rollback=auto_rollback)
        memory_manager.capture_snapshot()
        return res

    elif tool_name == "file_read":
        path = params.get("path", "")
        start_line = params.get("start_line")
        end_line = params.get("end_line")
        return executor.read_workspace_file(path, start_line=start_line, end_line=end_line)

    elif tool_name == "git_diff":
        path = params.get("path", "")
        return executor.get_workspace_git_diff(path)

    elif tool_name == "git_status":
        return await github_client.handle_github_action("status", params)

    elif tool_name == "git_log":
        return await github_client.handle_github_action("log", params)

    elif tool_name == "git_blame":
        return await github_client.handle_github_action("blame", params)

    elif tool_name == "git_branch":
        return await github_client.handle_github_action("branch", params)

    elif tool_name == "git_checkout":
        return await github_client.handle_github_action("checkout", params)

    elif tool_name == "git_clean":
        return await github_client.handle_github_action("clean", params)

    elif tool_name == "list_dir":
        path = params.get("path", "")
        max_depth = params.get("max_depth", 3)
        return executor.list_workspace_dir(path, max_depth=max_depth)

    elif tool_name == "get_outline":
        path = params.get("path", "")
        return executor.get_file_outline(path)

    elif tool_name == "search_codebase":
        query = params.get("query", "")
        path = params.get("path", "")
        include_pattern = params.get("include_pattern", "")
        max_results = int(params.get("max_results", 50))
        return executor.search_codebase(query, path=path, include_pattern=include_pattern, max_results=max_results)

    elif tool_name == "find_references":
        symbol = params.get("symbol", "")
        file_type = params.get("file_type", "")
        scope_dir = params.get("scope_dir", "")
        return executor.find_references(symbol, file_type=file_type, scope_dir=scope_dir)

    elif tool_name == "git_clone":
        return await github_client.handle_github_action("clone", params)

    elif tool_name == "git_pull":
        return await github_client.handle_github_action("pull", params)

    elif tool_name == "git_push":
        return await github_client.handle_github_action("push", params)

    elif tool_name == "capture_memory":
        snapshot = memory_manager.capture_snapshot()
        return {"status": "success", "output": "專案架構快照已更新", "snapshot": snapshot}

    elif tool_name == "list_tool":
        return {
            "status": "success",
            "total_tools": len(SUPPORTED_TOOLS),
            "tools": SUPPORTED_TOOLS,
            "exit_code": 0
        }

    else:
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
            return await _execute_single_tool(tool_name, params)

        # 支援批次陣列請求 (Fail-Fast pipeline)
        if isinstance(req, list):
            print(f"[Bridge] 收到批次指令請求，共 {len(req)} 項")
            batch_results = []
            for idx, item in enumerate(req):
                tool_name = item.tool
                params = item.parameters or {}
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
                    return {
                        "status": "failed",
                        "interrupted_at": idx + 1,
                        "total_steps": len(req),
                        "batch_results": batch_results,
                        "output": f"第 {idx + 1} 步執行失敗 ({tool_name})，已中止後續指令。",
                        "exit_code": exit_code if exit_code != 0 else -1
                    }

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
