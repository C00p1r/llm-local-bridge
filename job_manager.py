import os
import sys
import time
import uuid
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from config import WORKSPACE_DIR, get_scoped_workspace_dir, get_active_project

JOBS: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
_events_file = Path(WORKSPACE_DIR) / ".bridge" / "events.json"

def _tail_file(filepath: Path, n_lines: int = 15) -> str:
    if not filepath.exists():
        return ""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return "".join(lines[-n_lines:]).strip()
    except Exception as e:
        return f"[讀取記錄失敗: {e}]"

def _record_event(event_payload: dict):
    try:
        import json
        _events_file.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            events = []
            if _events_file.exists():
                try:
                    events = json.loads(_events_file.read_text(encoding="utf-8"))
                except Exception:
                    events = []
            events.append(event_payload)
            _events_file.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Bridge Async] 寫入 events.json 失敗: {e}")

def get_and_clear_events() -> list:
    """讀取並清空已產生的背景事件"""
    import json
    with _lock:
        if not _events_file.exists():
            return []
        try:
            events = json.loads(_events_file.read_text(encoding="utf-8"))
            _events_file.write_text("[]", encoding="utf-8")
            return events
        except Exception as e:
            print(f"[Bridge Async] 讀取 events.json 失敗: {e}")
            return []

def _job_supervisor(job_id: str, proc: subprocess.Popen, log_path: Path, notify: bool):
    start_time = time.time()
    returncode = proc.wait()
    elapsed = round(time.time() - start_time, 2)
    summary_log = _tail_file(log_path, n_lines=15)

    with _lock:
        job = JOBS.get(job_id)
        if job:
            job["status"] = "COMPLETED" if returncode == 0 else "FAILED"
            job["exit_code"] = returncode
            job["elapsed_seconds"] = elapsed
            job["summary_log"] = summary_log
            job["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            job_name = job.get("job_name", "")

    if notify:
        event_payload = {
            "event": "JOB_COMPLETED",
            "job_id": job_id,
            "job_name": job_name,
            "exit_code": returncode,
            "status": "COMPLETED" if returncode == 0 else "FAILED",
            "elapsed_seconds": elapsed,
            "summary_log": summary_log,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        _record_event(event_payload)

def start_async_job(command: str, job_name: Optional[str] = None, log_file: Optional[str] = None, notify_on_complete: bool = True) -> dict:
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    scoped_dir = get_scoped_workspace_dir()
    name = job_name or f"job_{job_id}"
    
    if log_file:
        log_p = (scoped_dir / log_file).resolve()
    else:
        log_dir = scoped_dir / ".bridge_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_p = log_dir / f"{job_id}.log"
    
    log_p.parent.mkdir(parents=True, exist_ok=True)

    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)

    try:
        f_out = open(log_p, "w", encoding="utf-8", errors="replace")
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(scoped_dir),
            stdout=f_out,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            close_fds=(sys.platform != "win32")
        )
    except Exception as e:
        return {
            "status": "error",
            "output": f"啟動非同步程序失敗: {str(e)}",
            "exit_code": -1
        }

    job_info = {
        "job_id": job_id,
        "job_name": name,
        "command": command,
        "pid": proc.pid,
        "status": "RUNNING",
        "exit_code": None,
        "log_file": str(log_p),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": 0,
        "notify_on_complete": notify_on_complete
    }

    with _lock:
        JOBS[job_id] = job_info

    thread = threading.Thread(target=_job_supervisor, args=(job_id, proc, log_p, notify_on_complete), daemon=True)
    thread.start()

    return {
        "status": "STARTED",
        "job_id": job_id,
        "job_name": name,
        "pid": proc.pid,
        "log_file": str(log_p),
        "notify_on_complete": notify_on_complete,
        "output": f"非同步工作已啟動 [ID: {job_id}, PID: {proc.pid}]。日誌將寫入: {log_p}",
        "exit_code": 0
    }

def poll_job(job_id: str) -> dict:
    with _lock:
        job = JOBS.get(job_id)
    if not job:
        return {
            "status": "not_found",
            "output": f"找不到工作 ID: {job_id}",
            "exit_code": -1
        }
    
    log_path = Path(job["log_file"])
    tail = _tail_file(log_path, n_lines=15)
    
    return {
        "status": "success",
        "job_id": job_id,
        "job_name": job["job_name"],
        "job_status": job["status"],
        "pid": job["pid"],
        "exit_code": job.get("exit_code"),
        "elapsed_seconds": job.get("elapsed_seconds"),
        "summary_log": tail,
        "output": f"工作狀態: {job['status']} (PID: {job['pid']})\n最新輸出日誌:\n{tail}",
        "exit_code_status": 0
    }
