import os
import secrets
from pathlib import Path

current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent

env_candidates = [current_dir / ".env", parent_dir / ".env"]
loaded_env = False

try:
    from dotenv import load_dotenv
    for p in env_candidates:
        if p.exists():
            load_dotenv(dotenv_path=p)
            loaded_env = True
            break
    if not loaded_env:
        load_dotenv()
except ModuleNotFoundError:
    for p in env_candidates:
        if p.exists():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
                break
            except Exception:
                pass

custom_workspace = os.getenv("WORKSPACE_DIR")
if custom_workspace:
    p = Path(custom_workspace)
    # 若為絕對路徑直接採用；若為相對路徑，強制以 current_dir 為基準
    WORKSPACE_DIR = p.resolve() if p.is_absolute() else (current_dir / p).resolve()
else:
    WORKSPACE_DIR = (current_dir / "workspace").resolve()

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

SESSION_TOKEN = os.getenv("SESSION_TOKEN") or secrets.token_urlsafe(16)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

ALLOWED_ORIGINS = [
    "https://chatgpt.com",
    "https://chat.openai.com",
    "https://gemini.google.com",
]

MAX_OUTPUT_CHARS = 8000
DEFAULT_TIMEOUT_SEC = 20