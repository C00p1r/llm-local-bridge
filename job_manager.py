import os
import sys
import time
import uuid
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from config import WORKSPACE_DIR, SANDBOX_IMAGE, get_scoped_workspace_dir, get_active_project
from sandbox import _get_docker_user_args

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

def _job_supervisor(job_id: str, container_name: str, log_path: Path, notify: bool):
    start_time = time.time()
    try:
        # 等待容器執行完畢並取得退出碼
        res = subprocess.run(["docker", "wait", container_name], capture_output=True, text=True)
        try:
            returncode = int(res.stdout.strip())
        except Exception:
            returncode = res.returncode if res.returncode != 0 else -1
    except Exception as e:
        print(f"[Bridge Async] 等待容器 {container_name} 異常: {e}")
        returncode = -1
    finally:
        # 清理已結束的沙盒容器
        subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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
    active_proj = get_active_project()
    name = job_name or f"job_{job_id}"
    
    if log_file:
        log_p = (scoped_dir / log_file).resolve()
    else:
        log_dir = scoped_dir / ".bridge_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_p = log_dir / f"{job_id}.log"
    
    log_p.parent.mkdir(parents=True, exist_ok=True)

    # 計算相對於工作區根目錄的路徑，供容器內重定向日誌
    workspace_abs = str(Path(WORKSPACE_DIR).resolve())
    try:
        rel_log_path = log_p.relative_to(Path(WORKSPACE_DIR)).as_posix()
        container_log_target = f"/workspace/{rel_log_path}"
    except ValueError:
        container_log_target = "/dev/null"

    container_workdir = f"/workspace/{active_proj}" if active_proj else "/workspace"
    container_name = f"llm_bridge_async_{job_id}"

    # 將執行指令與輸出重定向封裝為容器執行
    wrapped_command = f"{command} > {container_log_target} 2>&1"

    docker_args = [
        "docker", "run",
        "-d",
        "--name", container_name,
        "--network", "none",
        "--cpus", "6.0",
        "--memory", "6g",
        *(_get_docker_user_args()),
        "-v", f"{workspace_abs}:/workspace:rw",
        "-w", container_workdir,
        SANDBOX_IMAGE,
        "sh", "-c", wrapped_command
    ]

    try:
        # 以背景非同步方式啟動容器
        res = subprocess.run(docker_args, capture_output=True, text=True)
        if res.returncode != 0:
            return {
                "status": "error",
                "output": f"啟動 Docker 沙盒非同步容器失敗: {res.stderr.strip() or res.stdout.strip()}",
                "exit_code": res.returncode
            }
        container_id_short = res.stdout.strip()[:12]
    except FileNotFoundError:
        return {
            "status": "error",
            "output": "未在系統中找到 Docker，請確認 Docker Desktop / Daemon 是否已啟動。",
            "exit_code": -1
        }
    except Exception as e:
        return {
            "status": "error",
            "output": f"啟動非同步沙盒任務失敗: {str(e)}",
            "exit_code": -1
        }

    job_info = {
        "job_id": job_id,
        "job_name": name,
        "command": command,
        "container_name": container_name,
        "container_id": container_id_short,
        "pid": container_id_short,
        "status": "RUNNING",
        "exit_code": None,
        "log_file": str(log_p),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": 0,
        "notify_on_complete": notify_on_complete
    }

    with _lock:
        JOBS[job_id] = job_info

    thread = threading.Thread(target=_job_supervisor, args=(job_id, container_name, log_p, notify_on_complete), daemon=True)
    thread.start()

    return {
        "status": "STARTED",
        "job_id": job_id,
        "job_name": name,
        "container_name": container_name,
        "container_id": container_id_short,
        "pid": container_id_short,
        "log_file": str(log_p),
        "notify_on_complete": notify_on_complete,
        "output": f"非同步沙盒容器已啟動 [ID: {job_id}, Container: {container_name}]。日誌將寫入: {log_p}",
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
        "exit_code": 0,
        "job_exit_code": job.get("exit_code"),
        "elapsed_seconds": job.get("elapsed_seconds"),
        "summary_log": tail,
        "output": f"工作狀態: {job['status']} (PID: {job['pid']})\n最新輸出日誌:\n{tail}"
    }
