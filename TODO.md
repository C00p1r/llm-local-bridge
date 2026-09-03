# LLM Local Bridge - 開發進度與需求追蹤 (TODO)

## 循環開發工作原則
- **流程閉環**：Agent 修改 -> Push to GitHub -> 停下等待 -> 執行端 Pull 部署 -> 驗證測試 -> 回饋日誌/需求 -> Agent 修正。
- **先讀後改**：修改前必先使用 `read_file` 或讀取指令確認原檔上下文，禁止通篇覆寫與盲猜。
- **遠端同步停步**：Push 至 GitHub 後立即停下回報，嚴禁跨步預設執行端狀態。
- **如實追蹤錯誤**：執行端報錯、異常與權限問題逐字記錄分析，不隱瞞。

---

## 需求清單與進度

### [Phase 1: 診斷與精確編輯能力 (Completed)]
- [x] **`read_file`**：支援行號標註與 `start_line` / `end_line` 範圍擷取，杜絕換行轉義與盲猜。
- [x] **`git_diff`**：支援檢視工作區相較於 Git HEAD 的 unified diff，推送前確保修改乾淨。
- [x] **內建語法驗證 (Syntax Validation)**：無縫整合於 `replace_content` 與 `write_file`，寫入 `.py` 前自動執行 `ast.parse`，語法錯誤即時中斷回報。
- [x] **修復啟動錯誤**：補齊 `executor.py` 頂部 `from typing import Optional`。

### [Phase 2: 沙盒權限與結構化感知 (Completed)]
- [x] **沙盒 UID/GID 對齊與權限修復 (Permissions & Ownership)**
  - **實作**：在 `executor.py` 注入 `_get_docker_user_args()`，POSIX/WSL 動態對齊 `--user uid:gid`，避免 root 鎖定檔案。
- [x] **`list_dir` 結構化目錄樹**
  - **實作**：過濾 `.git`、`__pycache__`、`node_modules`、`.venv`，以緊湊目錄樹回傳，大幅省下 Token。
- [x] **`get_outline` 程式碼大綱感知**
  - **實作**：基於 AST 解析 `.py` 檔案之 class / function 簽名與行號範圍，快速定位 target。

### [Phase 3: RAG 模組與本機記憶檢索 (Planned)]
- [ ] **向量庫與檢索架構設計**：輕量化本機檢索與 CodeRAG 支援。
- [ ] **工作區上下文檢索 API**：提供切片與相關性搜尋工具。
