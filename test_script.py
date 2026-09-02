import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from config import GITHUB_TOKEN

repo = "C00p1r/llm-local-bridge"
target_dir = Path(".").resolve()
tree_items = []

for root, dirs, files in os.walk(target_dir):
    dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "node_modules", ".venv", "venv", "workspace"}]
    for file in files:
        if file in {".env", ".DS_Store", "Thumbs.db"} or file.endswith(".pyc"):
            continue
        if file.startswith(".bridge_memory"):
            continue
        full_path = Path(root) / file
        try:
            content = full_path.read_text(encoding="utf-8")
            rel_path = full_path.relative_to(target_dir).as_posix()
            tree_items.append({"path": rel_path, "mode": "100644", "type": "blob", "content": content})
        except Exception:
            pass

print(f"Total files to push: {len(tree_items)}")
for item in tree_items:
    print(f" - {item['path']}")

req = urllib.request.Request(
    f"https://api.github.com/repos/{repo}/git/trees",
    data=json.dumps({"tree": tree_items}).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "LLM-Local-Bridge",
        "Content-Type": "application/json"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as resp:
        print("Success! Tree SHA:", json.loads(resp.read().decode())["sha"])
except urllib.error.HTTPError as e:
    err_body = e.read().decode("utf-8")
    print("\n=== GitHub Detailed Error ===")
    try:
        parsed = json.loads(err_body)
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    except Exception:
        print(err_body)