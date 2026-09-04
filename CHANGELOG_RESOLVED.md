# Changelog & Release Notes

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
