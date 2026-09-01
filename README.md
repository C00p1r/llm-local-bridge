# LLM Local Bridge

一個讓網頁版 AI（ChatGPT、Google Gemini 等）具備本機工作區操作能力的橋接工具。透過瀏覽器使用者腳本（Tampermonkey）監聽 LLM 輸出的工具呼叫格式，並經由本機 FastAPI 伺服器在安全沙盒（Docker 斷網環境）中執行指令或寫入檔案，並由主機代管 Git 遠端同步，實現全自動本機開發與 GitHub 協同迴圈。

---

## 系統架構

```
[ Web LLM (ChatGPT / Gemini) ]
              │  (解析 tool_call 區塊)
              ▼
[ Tampermonkey Script (Browser) ]
              │  (HTTP POST /execute + Bearer Token)
              ▼
[ FastAPI Server (server.py) ]
              ├── write_file ──────> 本機 ./workspace (路徑穿越防護)
              ├── github_action ───> 主機端 Git CLI / REST API (Clone/Pull/Push)
              └── execute_command ──> Docker Sandbox (executor.py)
                                           │ (斷網 --network none、限制 CPU/RAM)
                                           ▼
                                     [ Container ]
```

---

## 專案結構

* `server.py`：本機 FastAPI 伺服器，負責權限驗證（Session Token）與工具請求派發。
* `executor.py`：指令執行器，透過 Docker 斷網沙盒（`python:3.11-slim`）安全隔離執行 Bash 指令。
* `github_client.py`：GitHub 協同模組，由主機端代為處理 `clone`、`fetch`、`pull`、`push_workspace` 及 REST API 操作。
* `memory_manager.py`：專案快照與記憶體管理，動態維護工作區目錄結構與環境狀態。
* `config.py`：環境與安全設定（工作區路徑、逾時時間、字數限制、Token 生成）。
* `launcher.py`：一鍵啟動腳本，自動檢查 Docker 與環境依賴。
* `tampermonkey_script.js`：瀏覽器使用者腳本，負責攔截對話、發送 API 並自動回填 `[TOOL_RESULT]`。
* `requirements.txt`：Python 後端依賴套件清單。

---

## 快速開始

### 1. 環境需求
* Python 3.10+
* Docker（用於指令沙盒執行）
* Git CLI（已安裝並加入系統 PATH）
* 瀏覽器 Tampermonkey 擴充功能

### 2. 安裝依賴
```bash
pip install -r requirements.txt
```

### 3. 啟動後端伺服器
```bash
python launcher.py
# 或使用 uvicorn 啟動
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```
*伺服器啟動時會在終端輸出本次生成的 `SESSION_TOKEN`。*

### 4. 設定 Tampermonkey
1. 將 `tampermonkey_script.js` 匯入瀏覽器的 Tampermonkey 擴充套件。
2. 將伺服器啟動時顯示的 Token 填入腳本設定中。
3. 開啟 ChatGPT 或 Gemini，系統將自動注入 Agent 提示詞與本機工作區快照。

---

## 支援工具格式

### 1. 終端指令 (`execute_command`)
在斷網沙盒中執行 Shell 指令（適用於檔案檢視、單元測試、本機運算）：
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
建立或覆寫工作區中的檔案（具備路徑防穿越機制）：
```json
{
  "tool": "write_file",
  "parameters": {
    "path": "example.py",
    "content": "print('Hello, world!')"
  }
}
```

### 3. GitHub / Git 操作 (`github_action`)
由主機連網環境代為執行 Git 操作或呼叫 GitHub REST API：

* **遠端拉取與同步 (`pull`)**：
```json
{
  "tool": "github_action",
  "parameters": {
    "action": "pull",
    "params": {
      "repo": "owner/repo",
      "branch": "main",
      "subfolder": "project_folder",
      "force_reset": false
    }
  }
}
```

* **複製倉庫 (`clone`)**：
```json
{
  "tool": "github_action",
  "parameters": {
    "action": "clone",
    "params": {
      "repo_url": "[https://github.com/owner/repo.git](https://github.com/owner/repo.git)",
      "target_subfolder": "project_folder"
    }
  }
}
```

* **推送工作區 (`push_workspace`)**：
```json
{
  "tool": "github_action",
  "parameters": {
    "action": "push_workspace",
    "params": {
      "repo": "owner/repo",
      "branch": "main",
      "message": "Commit message",
      "subfolder": "project_folder"
    }
  }
}
```

* **其他 API 支援**：`get_repo`、`list_issues`、`create_issue`、`create_pull_request`、`get_file`。

---

## 開發路線圖 (Roadmap)

1. **核心版本控制與 GitHub 深度整合 (GitHub & Git Integration) [已上線 / 持續優化]**
   - [x] 主機代管 Git 核心操作（`clone`、`pull`、`fetch`、`push_workspace`）。
   - [x] Docker 斷網沙盒安全隔離與主機網路操作分流架構。
   - [x] REST API 檔案樹同步備用機制（適用於未配置 `.git` 環境）。
   - [ ] 支援多分支切換（`checkout` / `switch`）與 Git Stash 工作流。
   - [ ] 自動建立 PR、Issue 模板與 Code Review 建議自動注入。

2. **可攜性與部署體驗 (Portability & Packaging)**
   - [ ] 提供單一二進位執行檔（PyInstaller / Go CLI），降低 Python 與 Docker 手動配置門檻。
   - [ ] 支援純本機無 Docker 輕量隔離模式（適用於無 Docker 權限的主機環境）。

3. **通訊與效能優化 (Latency & Communication)**
   - [ ] 優化瀏覽器使用者腳本與後端的通訊效率，降低 DOM 輪詢與輸入延遲。
   - [ ] 支援串流（Streaming）解析工具呼叫區塊，提早觸發後端執行。

4. **自主 Agent 迴圈與提示工程 (Autonomous Behavior & Context)**
   - [ ] 持續精煉 System Prompt，維持主動執行原則（嚴禁要求使用者手動複製貼上）。
   - [ ] 自動修剪過長工具輸出，防止上下文長度超限與記憶體浪費。

---

## 踩坑紀錄與已解決問題 (Troubleshooting & Known Issues)

| # | 類別 | 遭遇問題（坑點） | 根本原因 | 解決方案 / 最佳實踐 |
| :--- | :--- | :--- | :--- | :--- |
| **01** | **安全防護** | 宿主機路徑穿越風險 | LLM 可透過 `cat ../` 或相對路徑存取沙盒外敏感檔案 | 工作區全面以 Docker 沙盒隔離，路徑鎖定於 `/workspace`，後端寫檔實作路徑防穿越校驗 |
| **02** | **前端捕捉** | 連發指令漏抓第二條訊息 | 去重比對誤判、`isProcessing` 狀態未即時銜接 | 於 DOM 節點打上實體標記（`dataset.bridgeExecuted`）並加強輪詢防抖機制 |
| **03** | **前端效能** | Console 狂跳 JSON 解析 Warning | 解析失敗節點未打已讀標記，導致輪詢重複解析拋錯 | 加入「失敗即標記」機制，當次失敗直接略過，終結死循環報錯 |
| **04** | **字串傳輸** | Base64 寫檔失敗與 JSON 語法崩潰 | HTML/JS 包含大量引號、換行與 Markdown 轉義，破壞 Shell 與 JSON 結構 | 嚴禁在 Bash 硬塞多行程式碼，全面改由獨立 `write_file` API 傳遞內容 |
| **05** | **驗證通訊** | 後端重啟後 Tampermonkey 出現 `403 Forbidden` | 伺服器重啟預設動態生成全新 `SESSION_TOKEN` | 同步更新 Tampermonkey 的 Token；或於 `.env` 設定靜態 Token |
| **06** | **環境隔離** | 沙盒內無法執行 `git pull / push` | Docker 沙盒採 `--network none` 斷網且缺少 Host 憑證 | 將 Git 操作抽出為 `github_action`，改由主機端連網代管執行 |
| **07** | **版本控制** | Git CLI 拉取失敗或非 Git 目錄 | 本機未安裝 Git、未加 PATH 或工作區未初始化 `.git` | 實作雙軌制：優先呼叫本機 Git CLI，失敗自動降級為 GitHub REST API 檔案樹同步 |
| **08** | **檔案快取** | 程式碼修改後伺服器仍回傳「不支援此 Action」 | Python 記憶體快取舊模組，或工作區路徑層級寫錯位置 | 啟動加上 `--reload`；確認寫入路徑為當前執行的模組檔案 |
| **09** | **文件維護** | 更新 `README.md` 時誤刪重要章節 | 重寫文件時未先對照舊有章節結構 | 修改文件採「先讀取檢視、增量補充」原則，保留已知問題與歷史紀錄 |
