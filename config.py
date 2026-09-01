import os
import secrets
from pathlib import Path

# 1. 嘗試載入 .env
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

# 2. 工作區路徑設定（優先讀取 WORKSPACE_DIR 環境變數，預設為 current_dir / "workspace"）
custom_workspace = os.getenv("WORKSPACE_DIR")
if custom_workspace:
    WORKSPACE_DIR = Path(custom_workspace).resolve()
else:
    WORKSPACE_DIR = (current_dir / "workspace").resolve()

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

# 3. Session Token：優先採用 .env 設定，未設定則自動生成 16 bytes 安全 Token
SESSION_TOKEN = os.getenv("SESSION_TOKEN") or secrets.token_urlsafe(16)

# 4. GitHub PAT
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# 5. CORS 白名單（FastAPI 必須為 list 型別）
ALLOWED_ORIGINS = [
    "https://chatgpt.com",
    "https://chat.openai.com",
    "https://gemini.google.com",
]

# 6. 執行安全限制
MAX_OUTPUT_CHARS = 8000
DEFAULT_TIMEOUT_SEC = 20
