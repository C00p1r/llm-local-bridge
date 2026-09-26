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

def _job_supervisor(job_id: str, container_name: str, log_path: Path, notify: bool, timeout: Optional[int] = None):
    start_time = time.time()
    returncode = -1
    timed_out = False
    killed = False
    try:
        # 支援超時檢測的非阻塞輪詢等待
        while True:
            # 檢查容器是否仍在執行
            inspect_res = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
                capture_output=True,
                text=True
            )
            is_running = inspect_res.stdout.strip().lower() == "true"
            
            # 若容器已不在運行，取得其 ExitCode
            if not is_running:
                code_res = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.ExitCode}}", container_name],
                    capture_output=True,
                    text=True
                )
                try:
                    returncode = int(code_res.stdout.strip())
                except Exception:
                    returncode = 0
                break
            
            current_elapsed = time.time() - start_time
            with _lock:
                j = JOBS.get(job_id)
                if j and j.get("status") == "KILLED":
                    killed = True
                    break
                if j:
                    j["elapsed_seconds"] = round(current_elapsed, 1)
            
            # 檢查是否超時
            if timeout and current_elapsed > timeout:
                timed_out = True
                print(f"[Bridge Async] 任務 {job_id} 超過設定上限 {timeout}s，正在強制終止容器...")
                subprocess.run(["docker", "kill", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                returncode = 124
                break
            
            time.sleep(1.0)
    except Exception as e:
        print(f"[Bridge Async] 監控容器 {container_name} 異常: {e}")
        returncode = -1
    finally:
        # 清理沙盒容器
        subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    elapsed = round(time.time() - start_time, 2)
    
    # 若超時或被手動 kill，寫入提示至日誌檔案尾端
    if timed_out or killed:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                if timed_out:
                    f.write(f"\n[Bridge Async Error] 任務執行超時 (超過 {timeout} 秒限制)，已被守護行程強制終止。\n")
                elif killed:
                    f.write(f"\n[Bridge Async Warning] 任務已依指令被手動中斷 (Killed)。已耗時: {elapsed} 秒。\n")
        except Exception:
            pass

    summary_log = _tail_file(log_path, n_lines=15)

    with _lock:
        job = JOBS.get(job_id)
        if job:
            if killed:
                final_status = "KILLED"
                returncode = 137
            elif timed_out:
                final_status = "TIMEOUT"
            else:
                final_status = "COMPLETED" if returncode == 0 else "FAILED"
            
            job["status"] = final_status
            job["exit_code"] = returncode
            job["elapsed_seconds"] = elapsed
            job["summary_log"] = summary_log
            job["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            job_name = job.get("job_name", "")
        else:
            final_status = "FAILED"
            job_name = ""

    if notify:
        event_payload = {
            "event": "JOB_TIMEOUT" if timed_out else ("JOB_KILLED" if killed else "JOB_COMPLETED"),
            "job_id": job_id,
            "job_name": job_name,
            "exit_code": returncode,
            "status": final_status,
            "elapsed_seconds": elapsed,
            "summary_log": summary_log,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        _record_event(event_payload)

def start_async_job(command: str, job_name: Optional[str] = None, log_file: Optional[str] = None, notify_on_complete: bool = True, timeout: Optional[int] = None) -> dict:
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

    # 在日誌最前綴注入啟動資訊與時間戳記
    init_log_banner = f"[Bridge Async Job: {job_id} | Name: {name}]\nCommand: {command}\nStarted at: {time.strftime('%Y-%m-%d %H:%M:%S')}\nTimeout: {timeout if timeout else 'None'}\n{'-'*50}\n"
    try:
        log_p.write_text(init_log_banner, encoding="utf-8")
    except Exception:
        pass

    # 將執行指令與輸出重定向封裝為容器執行 (append 模式寫入日誌)
    wrapped_command = f"{command} >> {container_log_target} 2>&1"

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
        "start_timestamp": time.time(),
        "elapsed_seconds": 0,
        "timeout": timeout,
        "notify_on_complete": notify_on_complete
    }

    with _lock:
        JOBS[job_id] = job_info

    thread = threading.Thread(target=_job_supervisor, args=(job_id, container_name, log_p, notify_on_complete, timeout), daemon=True)
    thread.start()

    return {
        "status": "STARTED",
        "job_id": job_id,
        "job_name": name,
        "container_name": container_name,
        "container_id": container_id_short,
        "pid": container_id_short,
        "log_file": str(log_p),
        "timeout": timeout,
        "notify_on_complete": notify_on_complete,
        "output": f"非同步沙盒容器已啟動 [ID: {job_id}, Container: {container_name}, Timeout: {timeout or '無限制'}]。日誌將寫入: {log_p}",
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
    
    # 即時計算已耗時 (秒)
    if job["status"] == "RUNNING":
        start_ts = job.get("start_timestamp")
        elapsed = round(time.time() - start_ts, 1) if start_ts else job.get("elapsed_seconds", 0)
    else:
        elapsed = job.get("elapsed_seconds", 0)

    # 格式化便於人類與 LLM 閱讀的時間字串 (例如: 12m 34s 或 45.2s)
    if elapsed >= 60:
        m, s = divmod(int(elapsed), 60)
        elapsed_str = f"{m}m {s}s ({elapsed}s)"
    else:
        elapsed_str = f"{elapsed}s"
    
    log_path = Path(job["log_file"])
    tail = _tail_file(log_path, n_lines=15)
    
    timeout_info = f" (Timeout: {job.get('timeout')}s)" if job.get("timeout") else ""
    
    return {
        "status": "success",
        "job_id": job_id,
        "job_name": job["job_name"],
        "job_status": job["status"],
        "pid": job["pid"],
        "exit_code": 0,
        "job_exit_code": job.get("exit_code"),
        "elapsed_seconds": elapsed,
        "elapsed_time": elapsed_str,
        "summary_log": tail,
        "output": f"工作狀態: {job['status']}{timeout_info} | 已耗時: {elapsed_str} (PID: {job['pid']})\n最新輸出日誌:\n{tail}"
    }

def stop_async_job(job_id: str) -> dict:
    """強制終止背景執行的非同步工作"""
    with _lock:
        job = JOBS.get(job_id)
    if not job:
        return {
            "status": "not_found",
            "output": f"找不到工作 ID: {job_id}",
            "exit_code": -1
        }
    
    if job["status"] != "RUNNING":
        return {
            "status": "already_terminated",
            "output": f"工作 {job_id} 目前狀態為 {job['status']}，無需終止。",
            "job_status": job["status"],
            "exit_code": 0
        }
    
    container_name = job.get("container_name")
    # 標記為 KILLED
    with _lock:
        job["status"] = "KILLED"
    
    # 強制 kill 容器 (若環境支援 docker 則嘗試終止與移除)
    if container_name:
        try:
            res = subprocess.run(["docker", "kill", container_name], capture_output=True, text=True)
            subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode != 0 and "No such container" not in res.stderr:
                print(f"[Bridge Async] kill 容器失敗或已終止: {res.stderr}")
        except (FileNotFoundError, Exception) as e:
            print(f"[Bridge Async] 調用 docker kill 略過 (環境無 Docker 或已終止): {e}")

    # 更新耗時資訊
    start_ts = job.get("start_timestamp")
    elapsed = round(time.time() - start_ts, 1) if start_ts else job.get("elapsed_seconds", 0)
    
    with _lock:
        job["elapsed_seconds"] = elapsed
        job["exit_code"] = 137
        job["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    
    log_path = Path(job["log_file"])
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[Bridge Async Warning] 收到外部強制中止指令 (kill_job)，任務已被終止。總耗時: {elapsed}s\n")
    except Exception:
        pass

    return {
        "status": "success",
        "job_id": job_id,
        "job_name": job["job_name"],
        "job_status": "KILLED",
        "elapsed_seconds": elapsed,
        "output": f"已成功強制終止背景任務 [ID: {job_id}, Name: {job['job_name']}]，耗時: {elapsed}s。",
        "exit_code": 0
    }

def list_async_jobs(limit: int = 10) -> dict:
    """列出所有背景任務與其最新狀態與已耗時"""
    with _lock:
        all_jobs = list(JOBS.values())
    
    now = time.time()
    summaries = []
    for j in reversed(all_jobs[-limit:]):
        if j["status"] == "RUNNING":
            start_ts = j.get("start_timestamp")
            el = round(now - start_ts, 1) if start_ts else j.get("elapsed_seconds", 0)
        else:
            el = j.get("elapsed_seconds", 0)
        
        m, s = divmod(int(el), 60)
        el_str = f"{m}m {s}s" if el >= 60 else f"{el}s"
        
        summaries.append({
            "job_id": j["job_id"],
            "job_name": j["job_name"],
            "status": j["status"],
            "elapsed_time": el_str,
            "started_at": j.get("started_at"),
            "exit_code": j.get("exit_code")
        })
    
    lines = [f"總共 {len(all_jobs)} 項背景任務 (顯示最新 {len(summaries)} 項):"]
    for s in summaries:
        lines.append(f"- [{s['status']}] ID: {s['job_id']} | 名稱: {s['job_name']} | 耗時: {s['elapsed_time']} | 啟動時間: {s['started_at']}")
    
    return {
        "status": "success",
        "total_jobs": len(all_jobs),
        "jobs": summaries,
        "output": "\n".join(lines),
        "exit_code": 0
    }
