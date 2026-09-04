# LLM Local Bridge - 開發進度與需求追蹤 (TODO)

## 循環開發工作原則
- **流程閉環**：Agent 修改 -> Push to GitHub -> 停下等待 -> 執行端 Pull 部署 -> 驗證測試 -> 回饋日誌/需求 -> Agent 修正。
- **先讀後改**：修改前必先使用 `read_file` 或讀取指令確認原檔上下文，禁止通篇覆寫與盲猜。
- **遠端同步停步**：Push 至 GitHub 後立即停下回報，嚴禁跨步預設執行端狀態。
- **如實追蹤錯誤**：執行端報錯、異常與權限問題逐字記錄分析，不隱瞞。

---

## 需求清單與進度

### [Phase 4: 錯誤反饋反射機制與工具鏈正規化 (In Progress)]
- [x] **1. JSON 格式損壞快速反饋 (Syntax Error Reflection)**
  - **實作**：Tampermonkey 偵測到含 `"tool"` 但無法解析之字串時，不強行猜測，直接回報 `JSON_SYNTAX_ERROR` 並附帶標準格式範例引導自我修正。
- [x] **2. 未知工具呼叫反射 (Tool Not Found Reflection)**
  - **實作**：`server.py` 在遇到未知工具名稱時，透過 `difflib` 列出最接近的建議工具名稱，並附帶完整的 `SUPPORTED_TOOLS` 清單。
- [x] **3. `execute_command` 禁止 Git 指令攔截與導引**
  - **實作**：`server.py` 攔截 `execute_command` 中的 `git ` 指令，提示改用專屬 `github_action` 工具。
- [x] **4. 複合工具 `patch_and_test` 實作**
  - **實作**：在 `executor.py` 與 `server.py` 完成原子化 `patch_and_test` 封裝，並同步更新 `tampermonkey_script.js` 系統提示詞。