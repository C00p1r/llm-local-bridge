import asyncio
import os
import re
from pathlib import Path
from typing import Dict, Any
from config import WORKSPACE_DIR, MAX_OUTPUT_CHARS, DEFAULT_TIMEOUT_SEC, SESSION_TOKEN, GITHUB_TOKEN

BLOCKED_FILES = {'.env', '.env.local', '.env.production', 'id_rsa', 'id_ed25519'}
BLOCKED_EXTENSIONS = {'.pem', '.key', '.pfx', '.p12'}

def is_blocked_path(target_path: Path) -> bool:
    if target_path.name in BLOCKED_FILES:
        return True
    if target_path.suffix.lower() in BLOCKED_EXTENSIONS:
        return True
    return False

def redact_sensitive_info(text: str) -> str:
    if not text:
        return text
    
    # 遮蔽已知 Session Token 與 GitHub Token
    if SESSION_TOKEN and len(SESSION_TOKEN) > 6:
        text = text.replace(SESSION_TOKEN, "***SESSION_TOKEN_REDACTED***")
    if GITHUB_TOKEN and len(GITHUB_TOKEN) > 6:
        text = text.replace(GITHUB_TOKEN, "***GITHUB_TOKEN_REDACTED***")
        
    # 正則遮蔽常見 Token 格式與機密欄位
    text = re.sub(r'ghp_[a-zA-Z0-9]{30,}', '***GITHUB_PAT_REDACTED***', text)
    text = re.sub(r'github_pat_[a-zA-Z0-9_]{30,}', '***GITHUB_FINE_GRAINED_TOKEN_REDACTED***', text)
    text = re.sub(r'(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*[\'"]?([a-zA-Z0-9_.-]{12,})[\'"]?', r'\1: ***REDACTED***', text)
    return text

async def run_shell_command(command: str, timeout: int = DEFAULT_TIMEOUT_SEC) -> Dict[str, Any]:
    # 阻擋針對敏感檔案的讀取指令（使用 \\b 確保單字邊界）
    for blocked in BLOCKED_FILES:
        pattern = r'(?i)\b(cat|type|more|less|head|tail|Get-Content)\b.*' + re.escape(blocked)
        if re.search(pattern, command):
            return {
                "status": "error",
                "output": f"[Security Guard] 拒絕存取敏感設定檔: {blocked}",
                "exit_code": 403
            }

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORKSPACE_DIR)
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return {
                "status": "timeout",
                "output": f"[Executor] 指令執行逾時 ({timeout}s)",
                "exit_code": -1
            }
            
        raw_output = (stdout.decode('utf-8', errors='replace') + stderr.decode('utf-8', errors='replace')).strip()
        sanitized_output = redact_sensitive_info(raw_output)
        
        if len(sanitized_output) > MAX_OUTPUT_CHARS:
            sanitized_output = sanitized_output[:MAX_OUTPUT_CHARS] + f"\n... [Output truncated at {MAX_OUTPUT_CHARS} characters]"
            
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "output": sanitized_output,
            "exit_code": proc.returncode
        }
    except Exception as e:
        return {
            "status": "error",
            "output": f"[Executor] 執行失敗: {str(e)}",
            "exit_code": -1
        }
def write_workspace_file(file_path: str, content: str) -> Dict[str, Any]:
    try:
        target = (WORKSPACE_DIR / file_path).resolve()
        if not str(target).startswith(str(WORKSPACE_DIR.resolve())):
            return {'status': 'error', 'output': '[Security Guard] 嚴禁寫入工作區以外的路徑', 'exit_code': 403}
        if is_blocked_path(target):
            return {'status': 'error', 'output': f'[Security Guard] 拒絕寫入敏感設定檔: {target.name}', 'exit_code': 403}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return {'status': 'success', 'output': f'檔案 {file_path} 寫入成功', 'exit_code': 0}
    except Exception as e:
        return {'status': 'error', 'output': f'[Executor] 寫入檔案失敗: {str(e)}', 'exit_code': -1}
