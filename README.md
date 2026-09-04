# LLM Local Bridge

一個讓網頁版 AI（ChatGPT、Google Gemini 等）具備本機工作區操作能力的橋接工具。透過瀏覽器使用者腳本（Tampermonkey）監聽 LLM 輸出的工具呼叫格式，並經由本機 FastAPI 伺服器在安全沙盒（Docker 斷網環境）中執行指令或寫入檔案，並由主機代管 Git 遠端同步，實現全自動本機開發與 GitHub 協同迴圈。

---

## 系統架構

```
[ Web LLM (ChatGPT / Gemini) ]
              │  (解析 tool_call 區塊: 單一物件 or 批次陣列)
              ▼
[ Tampermonkey Script (Browser) ]
              │  (HTTP POST /execute + Bearer Token)
              ▼
[ FastAPI Server (server.py) ]
              ├── write_file ──────> 本機 ./workspace (路徑穿越防護 + LF 正規化)
              ├── run_script ──────> Docker Sandbox (自動暫存、沙盒執行、結束即銷毀)
              ├── execute_command ──> Docker Sandbox (executor.py, 斷網 --network none)
              └── github_action ───> 主機端 Git CLI / REST API (Clone/Pull/Push)
```

---

## 專案結構

* `server.py`：本機 FastAPI 伺服器，負責權限驗證（Session Token）、Docker 狀態自檢與工具請求派發（支援 Batch Array 與 Fail-Fast 機制）。
* `executor.py`：指令執行器，透過 Docker 斷網沙盒（`python:3.11-slim`）安全隔離執行 Bash 指令，支援暫存多語言腳本（`run_transient_script`）與 CRLF/LF 自動正規化。
* `github_client.py`：GitHub 協同模組，由主機端代為處理 `clone`、`fetch`、`pull`、`push_workspace` 及 REST API 操作。
* `memory_manager.py`：專案快照與記憶體管理，動態維護工作區目錄結構與環境狀態。
* `config.py`：環境與安全設定（工作區路徑、逾時時間、字數限制、Token 生成）。
* `launcher.py`：一鍵啟動腳本，自動檢查 Docker 與環境依賴。
* `tampermonkey_script.js`：瀏覽器使用者腳本 (v4.11.0)，負責攔截對話、解析單一/批次 Tool Call、回填 `[TOOL_RESULT]` 並顯示即時調用成功率 (Badge %)。
* `requirements.txt`：Python 後端依賴套件清單。

---

## 支援工具格式 (Tool Schemas)

### 1. 終端指令 (`execute_command`)
在斷網沙盒中執行 Shell 指令（適用於短指令、檔案檢視、套件檢查）：
```json
{
  "tool": "execute_command",
  "parameters": {
    "command": "ls -la",
    "timeout": 20
  }
}
```

### 2. 寫入檔案 (`write_file`)
建立或覆寫工作區中的檔案（具備路徑防穿越機制與自動 CRLF $\to$ LF 轉換）：
```json
{
  "tool": "write_file",
  "parameters": {
    "path": "example.py",
    "content": "print('Hello, world!')"
  }
}
```

### 3. 沙盒暫存腳本執行 (`run_script`)
直接在沙盒中執行多行程式碼（支援 `python`、`bash`、`sh`、`node`），自動建立隔離暫存檔並在執行結束後保證清理：
```json
{
  "tool": "run_script",
  "parameters": {
    "code": "import sys\nprint(f'Python: {sys.version}')",
    "language": "python",
    "timeout": 30
  }
}
```

### 4. 批次呼叫 (Batch Array Pipeline)
將多個相依或循序操作打包成一個陣列同時發送，後端循序執行並實施 **Fail-Fast** 機制（若某步失敗則立即中斷，避免產生髒狀態）：
```json
[
  {
    "tool": "write_file",
    "parameters": {"path": "test.txt", "content": "hello"}
  },
  {
    "tool": "run_script",
    "parameters": {"code": "cat test.txt", "language": "bash"}
  }
]
```

### 5. GitHub / Git 操作 (`github_action`)
由主機連網環境代為執行 Git 操作或呼叫 GitHub REST API：
* **推送工作區 (`push_workspace` / `push`)**：
```json
{
  "tool": "github_action",
  "parameters": {
    "action": "push",
    "repo": "owner/repo",
    "branch": "main",
    "message": "Commit message",
    "subfolder": "project_folder"
  }
}
```
* **遠端同步 (`pull`)**：
```json
{
  "tool": "github_action",
  "parameters": {
    "action": "pull",
    "branch": "main",
    "subfolder": "project_folder",
    "force_reset": false
  }
}
```
* **複製倉庫 (`clone`)**：
```json
{
  "tool": "github_action",
  "parameters": {
    "action": "clone",
    "repo_url": "[https://github.com/owner/repo.git](https://github.com/owner/repo.git)",
    "target_subfolder": "project_folder"
  }
}
```

---

## 快速開始

### 1. 環境需求
* Python 3.10+
* Docker（用於指令沙盒執行）
* Git CLI（已安裝並加入系統 PATH）
* 瀏覽器 Tampermonkey 擴充功能
* **ripgrep (`rg`)（選用 / 強烈推薦）**：
  * 用於提供 `search_codebase` 極速檢索能力。若未安裝，Bridge 會自動回退至 Python 原生走訪；若需檢索大型專案建議安裝：
    * Ubuntu / Debian: `sudo apt install ripgrep`
    * macOS: `brew install ripgrep`
    * Windows (Scoop / Winget): `winget install BurntSushi.ripgrep.MSVC` 或 `scoop install ripgrep`

### 2. Windows / WSL 整合安裝說明 (WSL Integration Guide)
若你在 Windows 平台上開發，強烈建議搭配 **WSL 2 (Windows Subsystem for Linux)** 與 **Docker Desktop**：

1. **啟用 WSL 2 與安裝 Linux 發行版**：
   ```powershell
   wsl --install
   wsl --set-default-version 2
   ```
2. **配置 Docker Desktop WSL 整合**：
   - 開啟 Docker Desktop 進入 `Settings` -> `General`，確認勾選 **Use the WSL 2 based engine**。
   - 進入 `Settings` -> `Resources` -> `WSL Integration`，開啟與你安裝的 Linux 發行版（如 Ubuntu）的整合。
3. **網路與路徑注意事項**：
   - Windows 主機與 WSL 2 共用本機網路迴圈（`127.0.0.1` / `localhost`）。FastAPI 伺服器運行於 `127.0.0.1:8000` 時，Tampermonkey 腳本可無縫連線。
   - 在 WSL 內執行時，工作區路徑可放在 WSL 內部原生檔案系統（如 `~/projects`）以獲得最佳 I/O 效能。

### 3. 安裝依賴
```bash
pip install -r requirements.txt
```

### 4. 啟動後端伺服器
```bash
python launcher.py
# 或使用 uvicorn 啟動
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

### 5. 設定 Tampermonkey
1. 將 `tampermonkey_script.js` 匯入瀏覽器的 Tampermonkey 擴充套件。
2. 將伺服器啟動時終端輸出的 Token 填入設定彈窗（腳本會自動儲存於 GM 儲存庫，無需每次對話重複輸入）。
3. 右下角即會常駐顯示狀態 Badge，例如 `Bridge: 5/5 (100.0%)`。

---

## 踩坑紀錄與最佳實踐 (Troubleshooting & Best Practices)

| # | 類別 | 遭遇問題 | 根本原因 | 解決方案 / 最佳實踐 |
| :--- | :--- | :--- | :--- | :--- |
| **01** | **安全防護** | 宿主機路徑穿越風險 | LLM 可透過 `cat ../` 或相對路徑存取沙盒外敏感檔案 | 工作區全面以 Docker 沙盒隔離，路徑鎖定於 `/workspace`，後端寫檔實作路徑防穿越校驗 |
| **02** | **前端捕捉** | 連發指令漏抓第二條訊息 | 去重比對誤判、`isProcessing` 狀態未即時銜接 | 於 DOM 節點打上實體標記（`dataset.bridgeExecuted`）並加強輪詢防抖機制 |
| **03** | **前端效能** | Console 狂跳 JSON 解析 Warning | 解析失敗節點未打已讀標記，導致輪詢重複解析拋錯 | 加入「失敗即標記」機制，當次失敗直接略過，終結死循環報錯 |
| **04** | **字串傳輸** | Base64 寫檔失敗與 JSON 語法崩潰 | HTML/JS 包含大量引號、換行與 Markdown 轉義，破壞 Shell 與 JSON 結構 | 嚴禁在 Bash 硬塞多行程式碼，全面改由獨立 `write_file` 或 `run_script` 傳遞 |
| **05** | **跨平台相容** | Windows 執行 Shell 出現 `$'\r'` 錯誤 | Windows 系統預設輸出 CRLF (`\r\n`)，容器內的 Linux Bash 解析時會把 `\r` 當成檔名一部分 | 在後端 `write_workspace_file` 與 `run_transient_script` 實作自動正規化，強制替換為 LF (`\n`) |
| **06** | **對話延遲** | 執行臨時除錯腳本需 3 輪對話 | 舊架構需手動歷經「寫入 $\to$ 執行 $\to$ 刪除」三次請求回傳 | 引入 `run_script` 暫存直譯器與 Batch Array 批次執行，縮短 70% 延遲 |
| **07** | **限流防護** | Gemini 出現 1095 錯誤與頻繁限流 | 快速連續回傳觸發對話歷史膨脹與前端 DOM 連續送出 | 加入 1800ms 冷卻防護，並以批次打包減少對話輪次 |
| **08** | **Git 結構相容** | `github_action` 參數巢狀層級過深 | LLM 容易遺漏或混淆外層 parameters 與內層 params 欄位結構 | 後端支援參數扁平化解析（Flat Payload 相容），直接讀取第一層 parameters |
| **09** | **遠端同步** | GitHub Push 發生 non-fast-forward 或憑證衝突 | 本機工作區與遠端 Commit 樹分岔，或 subfolder 路徑對映錯誤 | 於 Host 端加入強制重設與自動 Git pull/rebase 策略，並在 subfolder 精確隔離專案檔案 |
| **10** | **局部編輯** | 修改現有檔案全量覆寫易遺漏程式碼 | `write_file` 重寫數百行檔案易造成 Token 浪費與上下文截斷損毀 | 實作 `replace_content` 搭配嚴格唯一性（Strict Uniqueness）驗證與換行符正規化 |
