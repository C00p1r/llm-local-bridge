from typing import Dict, Any
from tools import register_tool, TOOL_CATALOG, SUPPORTED_TOOLS
import sandbox
import file_manager
import executor
import memory_manager

def register_core_handlers():
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
        return await sandbox.run_shell_command(cmd, timeout=timeout)

    @register_tool("run_script")
    async def _handle_run_script(params: Dict[str, Any]):
        code = params.get("code", "")
        language = params.get("language", "python")
        timeout = params.get("timeout", 30)
        return await sandbox.run_transient_script(code=code, language=language, timeout=timeout)

    @register_tool("file_write")
    async def _handle_file_write(params: Dict[str, Any]):
        path = params.get("path", "")
        content = params.get("content", "")
        return file_manager.write_workspace_file(path, content)

    @register_tool("file_replace")
    async def _handle_file_replace(params: Dict[str, Any]):
        path = params.get("path", "")
        target = params.get("target", "")
        replacement = params.get("replacement", "")
        return file_manager.replace_file_content(path, target, replacement)

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
        return file_manager.read_workspace_file(path, start_line=start_line, end_line=end_line)

    @register_tool("set_active_project")
    async def _handle_set_active_project(params: Dict[str, Any]):
        from config import set_active_project, get_scoped_workspace_dir
        project_path = params.get("project_path", "")
        res = set_active_project(project_path)
        if res.get("status") == "success":
            memory_manager.schedule_background_snapshot()
            return {
                "status": "success",
                "output": f"{res.get('message')}\n當前工作邊界: {res.get('current_scope')}",
                "active_project": res.get("active_project"),
                "current_scope": res.get("current_scope"),
                "exit_code": 0
            }
        else:
            return {
                "status": "error",
                "output": f"[Bridge] 設定專案目錄失敗: {res.get('message')}",
                "exit_code": -1
            }

    @register_tool("get_workspace_state")
    async def _handle_get_workspace_state(params: Dict[str, Any]):
        from config import get_active_project, get_scoped_workspace_dir, WORKSPACE_DIR
        import shutil, subprocess
        active = get_active_project()
        scoped_dir = get_scoped_workspace_dir()
        git_bin = shutil.which("git")
        branch = "none"
        is_dirty = False
        if git_bin and (scoped_dir / ".git").exists():
            try:
                b_res = subprocess.run([git_bin, "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(scoped_dir), capture_output=True, text=True, timeout=5)
                if b_res.returncode == 0:
                    branch = b_res.stdout.strip()
                s_res = subprocess.run([git_bin, "status", "--porcelain"], cwd=str(scoped_dir), capture_output=True, text=True, timeout=5)
                if s_res.returncode == 0 and s_res.stdout.strip():
                    is_dirty = True
            except Exception:
                pass
        return {
            "status": "success",
            "active_project": active,
            "scoped_path": str(scoped_dir),
            "workspace_root": str(WORKSPACE_DIR),
            "git_branch": branch,
            "git_dirty": is_dirty,
            "output": f"專案狀態: active_project='{active}' (路徑: {scoped_dir}), Git 分支='{branch}', Dirty={is_dirty}",
            "exit_code": 0
        }

    @register_tool("capture_memory")
    async def _handle_capture_memory(params: Dict[str, Any]):
        snapshot = await memory_manager.async_capture_snapshot()
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
