# Changelog & Release Notes

## v4.13.2 (2026-09-18)
- **Fix DeepSeek Send Button Misclicking Sidebar (`tampermonkey_script.js`)**: 修復 `getSendButton()` 的 DeepSeek 分支在全域 fallback 中誤抓側邊欄按鈕（新對話／歷史項目）的問題。移除危險的全域 `div[role="button"]:has(svg)` 查詢，改為嚴格以輸入框為錨點、由後往前尋找送出鍵，並排除位於 sidebar/nav/history/conversation 內的節點；找不到時回傳 `null` 交由 Enter 備援。
- **Send Button Readiness Retry**: `submitToLLM` 新增按鈕就緒重試（最多 6 次、每次 120ms），避免 DeepSeek 輸入後送出鍵尚未啟用即送出失敗。
- **Complete Enter Fallback Sequence**: Enter 備援改為派發完整 `keydown` / `keypress` / `keyup` 事件序列（含 `composed: true`），提升與框架事件處理的相容性。
- **Programmatic Submit Guard**: 新增 `isProgrammaticSubmit` 旗標，避免 `submitToLLM` 合成的 click / Enter 事件被全域監聽器再次攔截，消除重複送出與焦點錯亂。
- **Fix Prompt Newline Escaping**: 修正首次對話注入 Prompt 中 `---\\n` 被渲染為字面文字而非實際換行的問題。

## v4.13.1 (2026-09-18)
- **Fix Premature Tool Execution on DeepSeek (`tampermonkey_script.js`)**: 修復 DeepSeek 上模型尚未輸出完成 tool_call 即被提早執行的問題。新增「輸出穩定度檢測」機制，tool_call 文字需連續兩輪輪詢維持不變（`STABLE_THRESHOLD`）才視為輸出完成。
- **Peek-then-Consume Parsing**: 重構 `getNextToolCall(peek)` 支援窺視模式；偵測階段不再立即標記 `bridgeExecuted`，待輸出穩定後才正式消費，避免半成品或暫時無法解析的片段被提前執行或誤報語法錯誤。
- **Strengthen DeepSeek Streaming Detection**: 擴充 `isStreaming()` 的 DeepSeek 停止按鈕選擇器（涵蓋繁簡中英文、icon button、`stop-button`、`data-testid`），並新增生成中樣式容器備援判斷，降低生成中被誤判為完成的機率。
- **Increase Post-Result Cooldown**: 送出 `[TOOL_RESULT]` 後的輪詢冷卻由 1800ms 提高至 2500ms（`RESULT_COOLDOWN_MS`），避免 DeepSeek 回應較慢時搶先解析殘留內容所導致的「回應太快」問題。

## v4.13.0 (2026-09-18)
- **DeepSeek Web Platform Support (`tampermonkey_script.js`)**: 新增 `@match https://chat.deepseek.com/*` 支援，將 DeepSeek 網頁版納入橋接範圍，與 ChatGPT、Google Gemini 並列為三大支援平台。
- **Multi-Platform Adapter Layer**: 重構前端平台偵測與 DOM 適配層，加入 `deepseek` 平台分支，實作其專屬的輸入框定位 (`#chat-input` / `textarea[placeholder]`)、送出按鈕鎖定與模型回覆容器選取邏輯，並對應停止按鈕結構偵測。
- **Multi-Web Prompt Injection & Tool Execution**: 統一 ChatGPT / Gemini / DeepSeek 三平台的對話攔截、強制工具呼叫前綴注入 (`[TOOL CALL REQUIRE]`) 與 `[TOOL_RESULT]` 回填流程。

## v4.12.2 (2026-09-13)
- **Exclude Tool Results from Forced Prefix (`tampermonkey_script.js`)**: 在 `handleUserSend` 過濾 `[TOOL_RESULT]` 訊息，避免自動回填執行結果觸發點擊或輸入時被誤加 `[TOOL CALL REQUIRE]`，消除不必要的重複解析並恢復正常的生成速度。

## v4.12.1 (2026-09-13)
- **Continuous Forced Tool Call Prefixing (`tampermonkey_script.js`)**: 修復過往僅首則對話注入前綴的限制；改為全對話週期監聽，只要 ToolCall 處於開啟狀態，後續輸入均會自動追加 `[TOOL CALL REQUIRE]` 前綴，並避免重複注入 System Prompt。

## v4.12.0 (2026-09-13)
- **Forced Tool Call Mode (`tampermonkey_script.js`)**: 新增強制工具呼叫按鈕 (`⚡ ToolCall: ON/OFF`) 與 GM 儲存狀態持久化；開啟時自動為非指令輸入注入 `[TOOL CALL REQUIRE]` 前綴。
- **Strict Directives in System Prompt**: 在系統提示詞中補充第「五、強制工具呼叫規範」，指示模型偵測到該標示時必須直接輸出 `tool_call` 區塊完成任務，禁止純文字回覆。

## v4.11.0 (2026-09-04)
- **Tampermonkey Script v4.11.0 Upgrade**: 同步更新前端使用者腳本至 v4.11.0，正式支援擴充之安全 Git 工具鏈（status, log, blame, branch, clean, checkout）。
- **Git Tool Expansion (`git_checkout`, `git_branch`, `git_clean`)**: 完善 Git 工具鏈，新增 `git_checkout` 單檔復原與分支切換能力，修復 `git_diff` 在 Windows 上的路徑解析 (`WinError 267`)。
- **Robust GitHub Actions Integration**: 統一扁平化參數傳遞，修復 `git_push` 缺少 repo 參數與分支獲取 404 問題。
- **Documentation & Changelog Synchronization**: 更新 README 與 TODO 進度，確認 Phase 5 Git 功能完備與高風險指令隔離策略。

## v4.9.0 (2026-09-03)
- **Docker Sandbox Permission Alignment**: 動態注入 `_get_docker_user_args` (`--user <uid>:<gid>`)，防止容器以 root 建立檔案鎖死宿主機 Python 讀寫權限 (`PermissionDenied`)。
- **Structured Tree Perception (`list_dir`)**: 實作輕量目錄樹掃描，自動排除 `.git`、`__pycache__`、`node_modules`、`.venv` 等噪音目錄，大幅節省 context token。
- **AST Code Outline Perception (`get_outline`)**: 支援基於 AST 解析 Python 原始碼之 Class、Function、Method 名稱與行號區間，協助 `replace_content` 快速精準鎖定目標字串。
- **Git Diff Robustness Safeguard**: 修復 `get_workspace_git_diff` 在 `res.stdout` 或 `res.stderr` 為 `None` 時引發的 `'NoneType' object has no attribute 'strip'` 異常。
- **System Prompt & Schemas Sync**: 更新 Tampermonkey 前端腳本，補齊 `list_dir` 與 `get_outline` 工具 Schema 定義與呼叫範例。

## v4.8.1 (2026-09-03)
- **Complete Tool Schemas in System Prompt**: Fully specified parameter types, required/optional flags, and default values for `execute_command`, `write_file`, `run_script`, and `github_action` in Tampermonkey's injected instruction.
- **Metric Accuracy Percentage Display**: Updated the floating status badge to display real-time success rate with percentage formatting (`Bridge: 5/5 (100.0%)`).
- **Batch Array Parser Compatibility**: Frontend regex and fallback bracket extractors now seamlessly handle JSON array payloads (`[...]`) for batch pipeline calls.
- **CRLF to LF Line Normalization**: Enforced strict POSIX line ending normalization in `write_workspace_file` and `run_transient_script` to eliminate carriage return syntax errors in containerized Linux Bash executions.
- **Transient Sandbox Execution (`run_script`)**: Introduced Python/Bash script execution with automated lifecycle cleanup, reducing round-trip dialog latency by up to 70%.

## v4.7.1 (2026-09-02)
- **Fix Regex Escaping in Tampermonkey Script**: Resolved literal unescaped newlines in `unescapeJsonString` causing syntax parse errors.
- **Throttle & Cooldown Safeguard**: Extended poll interval to 1200ms and added an 1800ms cooldown after execution to prevent triggering Gemini rate-limits and `Something went wrong (1095)` errors.
- **Unescape Sanitization**: Refined multiline JSON parsing and parameter decoding.

## v4.7 (2026-09-02)
- **System Prompt Safeguard**: Added strict constraints prohibiting multi-line inline scripts in `execute_command` (to avoid outer shell quotation syntax errors). Clarified the 2-step runner workflow (`write_file` -> `execute_command`).
- **Tool Calling Success Rate Indicator**: Integrated a persistent floating badge and GM storage counter in Tampermonkey script displaying realtime success rate `Tools: X% (success/total)`.
- **Unescape & Boundary Hardening**: Full non-greedy matching for parameter extraction and JSON character unescaping in Track 3.

## Known Issues & Ongoing Investigations
- **Gemini API Error (1095)**: 發生於「長對話紀錄 + 快速連續回應」情境，可能涉及 token 膨脹或網頁端 DOM 更新過載。
- **Tool Calling Rate Limit**: 短時間內高頻調用工具容易觸發前端或後端限流，已透過 1800ms 冷卻防護與 Batch Array 機制有效降低輪詢頻率。
