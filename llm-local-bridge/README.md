# LLM Local Bridge

一個將網頁端 AI（ChatGPT、Google Gemini 等）轉化為本機自動化 Agent 的輕量級橋接工具。透過瀏覽器使用者腳本（Tampermonkey）即時攔截並解析 LLM 輸出的工具呼叫格式（`tool_call`），傳送至本地 FastAPI 服務端，安全地在指定工作區內執行終端指令、讀寫檔案與 GitHub 遠端同步。

---

## 系統架構

```text
[ Web LLM (ChatGPT / Gemini) ]
              │  (解析 tool_call 區塊)
              ▼
[ Tampermonkey Script (Browser) ]
              │  (HTTP POST /execute + Bearer Token)
              ▼
[ FastAPI Server (server.py) ]
              ├── write_file ────> 本地工作區 (含路徑逃逸防護 & 敏感檔保護)
              ├── execute_command > 非同步本機指令 (含指令黑名單 & Token 自動脫敏)
              └── github_action ──> GitHub REST API (單檔 Commit / 全目錄 Push / 讀取遠端檔案)
```

---

## 模組說明

* `server.py`：核心 FastAPI 伺服器，負責權限驗證（Session Token）、請求分發與統一輸出規範。
* `executor.py`：指令與檔案操作執行器，內建安全守衛（阻擋敏感檔案讀寫、路徑逃逸攔截）與輸出脫敏（Redaction）機制。
* `github_client.py`：基於 `httpx` 的 GitHub API 整合客戶端，支援單檔增量提交 (`commit_file`)、全工作區推送 (`push_workspace`) 與遠端檔案讀取 (`get_remote_file`)。
* `config.py`：環境與配置中心，自動讀取 `.env` 並動態管理工作區路徑、逾時時間與 Token。
* `memory_manager.py`：工作區記憶體與狀態管理。
* `tampermonkey_script.js`：瀏覽器端腳本，負責監聽對話、發送 API 並自動將結果以 `[TOOL_RESULT]` 格式回填至對話框。
* `requirements.txt`：Python 相依套件清單（已全面移轉至 `httpx`，無需 `python-dotenv`）。

---

## 快速開始

### 1. 環境需求
* Python 3.10+
* 支援 Tampermonkey 擴充功能的瀏覽器（Chrome, Edge, Firefox 等）

### 2. 安裝依賴
```bash
pip install -r requirements.txt
```

### 3. 環境設定 (.env)
複製 `.env.example` 為 `.env` 並填入設定：
```env
SESSION_TOKEN=your_secure_random_token
GITHUB_TOKEN=ghp_your_personal_access_token
```

### 4. 啟動伺服器
```bash
python server.py
```

### 5. 瀏覽器端設定
1. 將 `tampermonkey_script.js` 匯入瀏覽器的 Tampermonkey。
2. 設定腳本內的 `API_TOKEN` 為伺服器產生的 `SESSION_TOKEN`。
3. 開啟 ChatGPT 或 Gemini，系統將自動注入 Agent 系統提示並進入協同狀態。

---

## 支援工具格式

### 1. 終端指令 (`execute_command`)
```json
{
  "tool": "execute_command",
  "parameters": {
    "command": "python test.py",
    "timeout": 20
  }
}
```

### 2. 寫入檔案 (`write_file`)
```json
{
  "tool": "write_file",
  "parameters": {
    "path": "example.py",
    "content": "print('Hello, world!')"
  }
}
```

### 3. GitHub 操作 (`github_action`)
* **單檔提交**：
```json
{
  "tool": "github_action",
  "parameters": {
    "action": "commit_file",
    "params": {
      "repo": "owner/repo",
      "file_path": "relative/path/to/file",
      "message": "commit message",
      "branch": "main"
    }
  }
}
```
* **全工作區推送**：
```json
{
  "tool": "github_action",
  "parameters": {
    "action": "push_workspace",
    "params": {
      "repo": "owner/repo",
      "branch": "main",
      "message": "Sync workspace"
    }
  }
}
```
* **遠端檔案讀取**：
```json
{
  "tool": "github_action",
  "parameters": {
    "action": "get_remote_file",
    "params": {
      "repo": "owner/repo",
      "file_path": "path/to/file",
      "branch": "main"
    }
  }
}
```

---

## 安全守衛與防護機制

* **敏感設定檔阻擋**：嚴格禁止終端存取或覆寫 `.env*`、`.pem`、`.key`、`id_rsa` 等機密檔案。
* **終端輸出脫敏**：自動識別並遮蔽 `SESSION_TOKEN`、`GITHUB_TOKEN`、GitHub PAT 及正則匹配的機密金鑰。
* **路徑逃逸防護**：檔案讀寫限制於宣告之工作區內，防止跨目錄攻擊。
