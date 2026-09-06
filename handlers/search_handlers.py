from typing import Dict, Any
from tools import register_tool
import search_ops

def register_search_handlers():
    @register_tool("list_dir")
    async def _handle_list_dir(params: Dict[str, Any]):
        path = params.get("path", "")
        max_depth = params.get("max_depth", 3)
        return search_ops.list_workspace_dir(path, max_depth=max_depth)

    @register_tool("get_outline")
    async def _handle_get_outline(params: Dict[str, Any]):
        path = params.get("path", "")
        return search_ops.get_file_outline(path)

    @register_tool("search_codebase")
    async def _handle_search_codebase(params: Dict[str, Any]):
        query = params.get("query", "")
        path = params.get("path", "")
        include_pattern = params.get("include_pattern", "")
        max_results = int(params.get("max_results", 50))
        return search_ops.search_codebase(query, path=path, include_pattern=include_pattern, max_results=max_results)

    @register_tool("find_references")
    async def _handle_find_references(params: Dict[str, Any]):
        symbol = params.get("symbol", "")
        file_type = params.get("file_type", "")
        scope_dir = params.get("scope_dir", "")
        return search_ops.find_references(symbol, file_type=file_type, scope_dir=scope_dir)
