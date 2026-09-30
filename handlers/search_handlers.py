import asyncio
from typing import Dict, Any
from tools import register_tool
import search_ops

def register_search_handlers():
    @register_tool("list_dir")
    async def _handle_list_dir(params: Dict[str, Any]):
        path = params.get("path", "")
        max_depth = params.get("max_depth", 3)
        return await asyncio.to_thread(search_ops.list_workspace_dir, path, max_depth=max_depth)

    @register_tool("get_outline")
    async def _handle_get_outline(params: Dict[str, Any]):
        path = params.get("path", "")
        return await asyncio.to_thread(search_ops.get_file_outline, path)

    @register_tool("grep_code")
    async def _handle_grep_code(params: Dict[str, Any]):
        query = params.get("query", "")
        path = params.get("path", "")
        include_pattern = params.get("include_pattern", "")
        context_lines = int(params.get("context_lines", 2))
        max_results = int(params.get("max_results", 50))
        offset = int(params.get("offset", 0))
        fixed_strings = bool(params.get("fixed_strings", False))
        case_sensitive = params.get("case_sensitive", None)
        return await asyncio.to_thread(
            search_ops.grep_code,
            query,
            path=path,
            include_pattern=include_pattern,
            context_lines=context_lines,
            max_results=max_results,
            offset=offset,
            fixed_strings=fixed_strings,
            case_sensitive=case_sensitive
        )

    @register_tool("find_definition")
    async def _handle_find_definition(params: Dict[str, Any]):
        symbol = params.get("symbol", "")
        path = params.get("path", params.get("scope_dir", ""))
        file_type = params.get("file_type", "")
        return await asyncio.to_thread(search_ops.find_definition, symbol, path=path, file_type=file_type)

    @register_tool("search_codebase")
    async def _handle_search_codebase(params: Dict[str, Any]):
        query = params.get("query", "")
        path = params.get("path", "")
        include_pattern = params.get("include_pattern", "")
        context_lines = int(params.get("context_lines", 2))
        max_results = int(params.get("max_results", 50))
        offset = int(params.get("offset", 0))
        fixed_strings = bool(params.get("fixed_strings", False))
        case_sensitive = params.get("case_sensitive", None)
        return await asyncio.to_thread(
            search_ops.search_codebase,
            query,
            path=path,
            include_pattern=include_pattern,
            context_lines=context_lines,
            max_results=max_results,
            offset=offset,
            fixed_strings=fixed_strings,
            case_sensitive=case_sensitive
        )

    @register_tool("find_references")
    async def _handle_find_references(params: Dict[str, Any]):
        symbol = params.get("symbol", "")
        path = params.get("path", params.get("scope_dir", ""))
        file_type = params.get("file_type", "")
        return await asyncio.to_thread(search_ops.find_references, symbol, path=path, file_type=file_type)
