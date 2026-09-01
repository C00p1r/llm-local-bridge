import uvicorn
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import executor
import github_client
import memory_manager
from config import SESSION_TOKEN, ALLOWED_ORIGINS

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

async def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="[Bridge] 缺少或無效的 Authorization 標頭")
    token = authorization.split(" ")[1]
    if token != SESSION_TOKEN:
        raise HTTPException(status_code=403, detail="[Bridge] Session Token 不正確")
    return token

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "[Bridge] 伺服器運行正常"}

@app.get("/context")
async def get_context(token: str = Depends(verify_token)):
    snapshot = memory_manager.capture_snapshot()
    prompt_text = memory_manager.get_latest_context_prompt()
    return {
        "status": "success",
        "snapshot": snapshot,
        "context_prompt": prompt_text
    }

@app.post("/execute")
async def execute_tool(req: ExecuteRequest, token: str = Depends(verify_token)):
    tool_name = req.tool
    params = req.parameters or {}
    print(f"[Bridge] 收到執行請求: {tool_name}")

    try:
        if tool_name == "execute_command":
            cmd = params.get("command", "")
            timeout = params.get("timeout", 30)
            result = await executor.run_shell_command(cmd, timeout=timeout)
            return result

        elif tool_name == "write_file":
            path = params.get("path", "")
            content = params.get("content", "")
            result = executor.write_workspace_file(path, content)
            memory_manager.capture_snapshot()
            return result

        elif tool_name == "github_action":
            action = params.get("action", "")
            sub_params = params.get("params", {})
            result = await github_client.handle_github_action(action, sub_params)
            return result

        elif tool_name == "capture_memory":
            snapshot = memory_manager.capture_snapshot()
            return {"status": "success", "output": "專案架構快照已更新", "snapshot": snapshot}

        else:
            return {"status": "error", "output": f"[Bridge] 未知的工具名稱: {tool_name}", "exit_code": -1}

    except Exception as e:
        print(f"[Bridge] 執行錯誤: {e}")
        return {"status": "error", "output": f"[Bridge] 伺服器內部錯誤: {str(e)}", "exit_code": -1}

if __name__ == "__main__":
    print(f"[Bridge] 🚀 Server 啟動於 127.0.0.1:8000 (Token: {SESSION_TOKEN})")
    memory_manager.capture_snapshot()
    uvicorn.run(app, host="127.0.0.1", port=8000)
