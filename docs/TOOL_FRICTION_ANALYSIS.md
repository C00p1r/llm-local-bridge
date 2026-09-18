# Bridge 工具使用摩擦點分析與擴充建議

> 產生時間：2026-09-18
> 來源：DeepSeek 多平台修復會話（v4.13.0 → v4.13.2）實測經驗

---

## 一、本次會話實際遭遇的摩擦點

### 1. tool_call JSON 解析失敗（最高頻，影響最大）
- **現象**：當批次 payload 內含大量引號、反斜線、換行時（尤其 file_write 寫入含引號的 Python／JS 程式碼），經常觸發 `JSON_SYNTAX_ERROR`。
- **實際案例**：本會話中至少有 4 次以上批次指令因跳脫字元失敗，被迫拆成單筆重試。
- **根因**：前端以 `JSON.parse` 解析 LLM 輸出的 tool_call 區塊；長字串中的 `\n`、`\"`、反斜線序列極易在傳輸層被二次轉義而破壞結構。
- **影響**：浪費對話輪次、增加限流風險、降低成功率指標。

### 2. 沙盒環境缺少 node 與 git
- **現象**：`execute_command` 在斷網 Docker 沙盒中執行，`node` 與 `git` 皆不存在。
- **後果**：
  - 無法對 `tampermonkey_script.js` 做真正的 JS 語法檢查（只能自寫 Python 括號平衡器近似驗證）。
  - 自寫的檢查器本身又受 JSON 跳脫問題困擾，多次誤報。
- **影響**：無法在提交前確保 JS 語法正確，只能靠人工推演。

### 3. git_push 後本地 HEAD 未同步
- **現象**：`git_push` 走 GitHub REST API 提交，本地 `.git` 的 HEAD 不會更新。
- **後果**：push 後 `git_status` 仍顯示檔案為 modified，必須再執行一次 `git_pull --force_reset` 才能對齊。
- **影響**：多一步驟、易誤判為推送失敗。

### 4. 缺少「提交前差異預覽」與「回滾」的輕量工具
- `git_diff` 可看工作區差異，但無法針對單一 staged patch 預覽。
- `patch_and_test` 有 `auto_rollback`，但一般 `file_replace` 誤改後無一鍵還原（需靠 git checkout）。

### 5. 長字串內容傳輸成本高
- 寫入一個中型檔案（數百行）需完整輸出內容，Token 消耗大且易出錯。
- 局部替換（file_replace）雖已緩解，但仍需精確重現 target 字串，含換行的 target 極易不匹配。

---

## 二、是否需要更多工具？——建議清單

| 優先級 | 建議工具 | 用途 | 解決的摩擦點 |
|:---:|:---|:---|:---|
| **P0** | `apply_patch`（unified diff 格式） | 以標準 unified diff 套用變更，取代長字串 file_replace | #1 #5 |
| **P0** | `lint_file` / `validate_syntax` | 支援 js/ts/py 語法檢查，於主機端執行（非斷網沙盒） | #2 |
| **P1** | `run_on_host` | 在主機連網環境執行指令（可選白名單），供 git／node 等使用 | #2 |
| **P1** | `file_undo` | 針對單一檔案或上一次操作一鍵還原 | #4 |
| **P2** | `search_replace_multi` | 一次多處精確替換，減少往返 | #5 |
| **P2** | `json_repair`（後端解析強化） | 前端解析失敗時，後端以寬鬆策略修復常見跳脫錯誤 | #1 |

### 針對 #1 的替代方案（不需新工具，改後端）
- 後端 `parseMultiLineJson` 增加「寬鬆模式」：自動修復未轉義的換行、多餘逗號、單引號等。
- 或在系統提示詞中明確要求：**批次 payload 若含程式碼，改用 run_script 或拆為單筆 file_write**。

### 針對 #2 的替代方案（不需新工具，改映像）
- 將沙盒映像由 `python:3.11-slim` 換為預裝 `node`、`git`、`ripgrep` 的映像，即可讓 lint／語法檢查在既有 `execute_command` 內完成。

---

## 三、結論

1. **最痛點是 tool_call JSON 跳脫問題（#1）**，且它連帶放大了其他摩擦（無法寫長檔、需反覆拆小）。建議**優先從後端解析強化 + 提示詞約束**著手，成本最低、見效最快。
2. **語法驗證能力缺口（#2）** 可透過**擴充沙盒映像**解決，比新增工具更簡單。
3. 真正值得**新增的工具**首選 `apply_patch`（unified diff）與 `file_undo`，能顯著降低長字串傳輸與誤改風險。
4. `git_push` 後本地不同步（#3）屬設計取捨，建議在文件或工具回傳訊息中明確提示「push 後請執行 pull 對齊」，或讓 `git_push` 內部自動補一次本地 fetch/reset。
