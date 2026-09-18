from pathlib import Path
from typing import Optional
from config import WORKSPACE_DIR, DEFAULT_TIMEOUT_SEC

from sandbox import run_shell_command, run_transient_script
from file_manager import (
    write_workspace_file,
    replace_file_content,
    read_workspace_file,
    get_workspace_git_diff,
    _ensure_writable
)
from search_ops import (
    list_workspace_dir,
    get_file_outline,
    search_codebase,
    find_references
)

async def patch_and_test_file(path: str, target: str, replacement: str, test_command: str, timeout: int = DEFAULT_TIMEOUT_SEC, auto_rollback: bool = False) -> dict:
    """
    原子操作：精確替換內容 -> 語法驗證 -> 即時執行測試指令。
    若 auto_rollback 為 True 且測試失敗，則自動還原原檔。
    """
    target_path = (Path(WORKSPACE_DIR) / path).resolve()
    original_content = None
    if target_path.exists() and target_path.is_file():
        try:
            original_content = target_path.read_text(encoding='utf-8')
        except Exception:
            pass

    replace_res = replace_file_content(path, target, replacement)
    if replace_res.get("status") != "success":
        return {
            "status": "failed",
            "patch_applied": False,
            "file_path": path,
            "error": replace_res.get("output"),
            "output": f"[patch_and_test] 替換階段失敗: {replace_res.get('output')}",
            "exit_code": replace_res.get("exit_code", -1)
        }

    test_res = await run_shell_command(test_command, timeout=timeout)
    test_status = test_res.get("status")
    test_exit_code = test_res.get("exit_code", 0)
    is_test_success = (test_status == "success" and test_exit_code == 0)

    rolled_back = False
    if not is_test_success and auto_rollback and original_content is not None:
        try:
            _ensure_writable(target_path)
            target_path.write_text(original_content, encoding='utf-8', newline='\n')
            rolled_back = True
        except Exception as e:
            rolled_back = f"還原失敗: {str(e)}"

    output_msg = f"[patch_and_test] 檔案已更新: {path}\n[測試指令] {test_command}\n[測試狀態] {test_status} (exit_code: {test_exit_code})\n[測試輸出]\n{test_res.get('output', '')}"
    if rolled_back is True:
        output_msg += "\n\n[Notice] 由於測試失敗且 auto_rollback=True，檔案已自動還原回原始狀態。"
    elif isinstance(rolled_back, str):
        output_msg += f"\n\n[Warning] {rolled_back}"

    return {
        "status": "success" if is_test_success else "failed",
        "patch_applied": True if not rolled_back else False,
        "rolled_back": rolled_back,
        "file_path": path,
        "test_execution": test_res,
        "output": output_msg,
        "exit_code": test_exit_code
    }
