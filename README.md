# LLM Local Bridge

一個讓網頁版 AI（ChatGPT、Google Gemini 等）具備本機工作區操作能力的橋接工具。透過瀏覽器使用者腳本（Tampermonkey）監聽 LLM 輸出的工具呼叫格式，並經由本機 FastAPI 伺服器在安全沙盒（Docker）中執行指令或寫入檔案，實現自動化本機開發與操作迴圈。

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
              └── execute_command ──> Docker Sandbox (executor.py)
                                           │ (斷網、限制 CPU/RAM)
                                           ▼
                                     [ Container ]
```

---

## 專案結構

* `server.py`：本機 FastAPI 伺服器，負責權限驗證（Session Token）與工具請求派發。
* `executor.py`：指令執行器，透過 Docker 沙盒（`python:3.11-slim`）安全隔離執行 Bash 指令。
* `config.py`：環境與安全設定（工作區路徑、逾時時間、字數限制、Token 生成）。
* `tampermonkey_script.js`：瀏覽器使用者腳本，負責攔截對話、發送 API 並自動回填 `[TOOL_RESULT]`。
* `requirements.txt`：Python 後端依賴套件清單。

---

## 快速開始

### 1. 環境需求
* Python 3.10+
* Docker（用於指令沙盒執行）
* 瀏覽器 Tampermonkey 擴充功能

### 2. 安裝依賴
```bash
pip install -r requirements.txt
```

### 3. 啟動後端伺服器
```bash
uvicorn server:app --host 127.0.0.1 --port 8000
```
*伺服器啟動時會在終端輸出本次生成的 `SESSION_TOKEN`。*

### 4. 設定 Tampermonkey
1. 將 `tampermonkey_script.js` 匯入瀏覽器的 Tampermonkey 擴充套件。
2. 將伺服器啟動時顯示的 Token 填入腳本設定中。
3. 開啟 ChatGPT 或 Gemini，系統將自動注入 Agent 提示詞。

---

## 支援工具格式

### 1. 終端指令 (`execute_command`)
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
```json
{
  "tool": "write_file",
  "parameters": {
    "path": "example.py",
    "content": "print('Hello, world!')"
  }
}
```

---

## 未來規劃與目標 (Roadmap)

1. **可攜性與隨插即用 (Portability)**
   - 打包為單一執行檔（如 PyInstaller / Go CLI），降低 Docker 與 Python 環境設定門檻。
   - 支援無 Docker 模式（輕量本機虛擬目錄隔離）以提高跨平台部署彈性。

2. **延遲與效能優化 (Latency Optimization)**
   - 優化瀏覽器腳本與後端的通訊效率，減少 DOM 輪詢與輸入注入延遲。
   - 改善 LLM 思考到工具呼叫的銜接迴圈，支援串流（Streaming）解析以提早觸發執行。

3. **強化 LLM 工具呼叫自主性 (Prompt & Behavior Robustness)**
   - 精煉 System Prompt 與對話注入機制，強化 ChatGPT/Gemini 的自主行動意願。
   - 避免 LLM 頻繁要求使用者「手動修改」，確保其主動使用 `write_file` / `execute_command` 解決問題。

4. **GitHub 整合 (GitHub Integration)**
   - 內建 Git/GitHub 相關工作流程與授權支援（如自動 Clone、Commit、Push 與 PR 建立）。
   - 支援讀取 GitHub Issue/Repo 資訊，提升多專案協同開發體驗。

## 待掦捡受待駧更新 (Known Issues & TODO)

**1. 多行指令解析透成同步失敗detection Issue**
- **現象**：在 `system_executor` 域地送入含轉行登號（`\n`)的多行 Shell / Python 指令時，底屋的 ═ JSON ⛐ Shell Interpreter ⛐ Inline Script 多層轉義容易進成引號遥澤或語法截断（如  `{syntax: "unexpected ("'}`)。
- **9bcy�'�)����K��*y�b����&�`o�7�r����ᕍ�ѕ}����������ⷖ
Ϧk�����ա����͍ɥ�Ӿ�3��3�VӚ���/��ǒ��6�O����R����ɥѕ}ݽɭ�����}�������"X�	�͔�Ё�����䁕���������ˢ�3�������3���?�����ۖ��bO�ʋ�ꓚ�[�(
