import os
import json
import sys
import platform
from pathlib import Path
from datetime import datetime
from config import WORKSPACE_DIR

MEMORY_FILE = WORKSPACE_DIR / ".bridge_memory.json"

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", 
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache", "dist", "build"
}

def get_directory_tree(root_dir: Path, max_depth: int = 3, current_depth: int = 0) -> dict:
    if current_depth > max_depth or not root_dir.exists() or not root_dir.is_dir():
        return {}
    
    tree = {"files": [], "directories": {}}
    try:
        for item in sorted(root_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
            if item.name.startswith(".") and item.name not in [".env.example"]:
                continue
            if item.name in IGNORE_DIRS:
                continue
            
            if item.is_file():
                tree["files"].append(item.name)
            elif item.is_dir():
                tree["directories"][item.name] = get_directory_tree(item, max_depth, current_depth + 1)
    except PermissionError:
        pass
    return tree

def format_tree_text(tree: dict, prefix: str = "") -> str:
    lines = []
    for d_name, subtree in tree.get("directories", {}).items():
        lines.append(f"{prefix}📁 {d_name}/")
        lines.append(format_tree_text(subtree, prefix + "  "))
    for f_name in tree.get("files", []):
        lines.append(f"{prefix}📄 {f_name}")
    return "\n".join(filter(None, lines))

def capture_snapshot(project_name: str = "Workspace") -> dict:
    tree = get_directory_tree(WORKSPACE_DIR)
    tree_str = format_tree_text(tree)
    
    snapshot = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "project_name": project_name,
        "environment": {
            "os": platform.system(),
            "os_release": platform.release(),
            "python_version": sys.version.split()[0],
            "workspace_path": str(WORKSPACE_DIR.resolve())
        },
        "directory_tree": tree,
        "tree_summary": tree_str
    }
    
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Bridge] 寫入記憶檔案失敗: {e}")
        
    return snapshot

def get_latest_context_prompt() -> str:
    if not MEMORY_FILE.exists():
        snapshot = capture_snapshot()
    else:
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        except Exception:
            snapshot = capture_snapshot()
            
    env = snapshot.get("environment", {})
    tree_str = snapshot.get("tree_summary", "")
    updated = snapshot.get("updated_at", "N/A")
    
    return (
        f"\n[PROJECT SNAPSHOT (Last updated: {updated})]\n"
        f"- OS: {env.get('os')} ({env.get('os_release')})\n"
        f"- Python: {env.get('python_version')}\n"
        f"- Workspace: {env.get('workspace_path')}\n\n"
        f"[WORKSPACE STRUCTURE]\n"
        f"{tree_str if tree_str else '(Empty or Unscanned)'}\n"
    )
