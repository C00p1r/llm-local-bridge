from typing import Dict, Any
from tools import register_tool
import file_manager
import github_client

def register_git_handlers():
    @register_tool("git_diff")
    async def _handle_git_diff(params: Dict[str, Any]):
        path = params.get("path", "")
        return file_manager.get_workspace_git_diff(path)

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

    @register_tool("git_clone")
    async def _handle_git_clone(params: Dict[str, Any]):
        return await github_client.handle_github_action("clone", params)

    @register_tool("git_pull")
    async def _handle_git_pull(params: Dict[str, Any]):
        return await github_client.handle_github_action("pull", params)

    @register_tool("git_push")
    async def _handle_git_push(params: Dict[str, Any]):
        return await github_client.handle_github_action("push", params)
