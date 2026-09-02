# Changelog & Release Notes

## v4.7 (2026-09-02)
- **System Prompt Safeguard**: Added strict constraints prohibiting multi-line inline scripts in `execute_command` (to avoid outer shell quotation syntax errors). Clarified the 2-step runner workflow (`write_file` -> `execute_command`).
- **Tool Calling Success Rate Indicator**: Integrated a persistent floating badge and GM storage counter in Tampermonkey script displaying realtime success rate `Tools: X% (success/total)`.
- **Unescape & Boundary Hardening**: Full non-greedy matching for parameter extraction and JSON character unescaping in Track 3.
## Known Issues & Ongoing Investigations
- **Gemini API Error (1095)**: 發生於「長對話紀錄 + 快速連續回應」情境，可能涉及 token 膨脹或網頁端 DOM 更新過載。
- **Tool Calling Rate Limit**: 短時間內高頻調用工具容易觸發前端或後端限流，需在 Tampermonkey 端評估加入請求節流（throttle/debounce）機制。