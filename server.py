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

async def _execute_single_tool(tool_name: str, params: Dict[str, Any]) -> dict:
    if tool_name == "execute_command":
        cmd = params.get("command", "")
        timeout = params.get("timeout", 30)
        return await executor.run_shell_command(cmd, timeout=timeout)

    elif tool_name == "run_script":
        code = params.get("code", "")
        language = params.get("language", "python")
        timeout = params.get("timeout", 30)
        res = await executor.run_transient_script(code=code, language=language, timeout=timeout)
        memory_manager.capture_snapshot()
        return res

    elif tool_name == "write_file":
        path = params.get("path", "")
        content = params.get("content", "")
        res = executor.write_workspace_file(path, content)
        memory_manager.capture_snapshot()
        return res

    elif tool_name == "replace_content":
        path = params.get("path", "")
        target = params.get("target", "")
        replacement = params.get("replacement", "")
        res = executor.replace_file_content(path, target, replacement)
        memory_manager.capture_snapshot()
        return res

    elif tool_name == "github_action":
        action = params.get("action", "")
        raw_sub = params.get("params")
        if isinstance(raw_sub, dict):
            sub_params = raw_sub
        else:
            sub_params = {k: v for k, v in params.items() if k != "action"}
        return await github_client.handle_github_action(action, sub_params)

    elif tool_name == "capture_memory":
        snapshot = memory_manager.capture_snapshot()
        return {"status": "success", "output": "專案架構快照已更新", "snapshot": snapshot}

    else:
        return {"status": "error", "output": f"[Bridge] 未知的工具名稱: {tool_name}", "exit_code": -1}

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
