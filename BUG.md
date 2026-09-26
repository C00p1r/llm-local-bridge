### LLM 已知BUG 列表
- [x] gemini側邊欄開啟的狀況下無法按下發送按鈕(此bug原本是會按下側邊欄對話紀錄的三個點按鈕)
- [x] poll_job_status 在正確回傳狀態(status=success)的情況下batch array卻顯示status=false，導致後續動作無法被中斷
- [x] 前端至後端 Bridge 工具傳輸層 XML/HTML 字元吞食導致語法毀損 (v4.15.3 移除破壞性角括號正則)

問題現象：

當 LLM 呼叫 file_replace、file_write 或 run_script 時，若參數字串中包含小於符號 <（例如 if len(combos) < config.combo_size: 或 config.max_pair_corr < 1.0），傳輸到後端時 < 及其後續部分常被解析器當作 XML 標籤吃掉，變成殘缺的 if len(combos)  thresh:。

隨後 Bridge 內建的語法驗證（Python AST check）在寫入前觸發 invalid syntax (line 289)，導致 file_replace 與 file_write 無法完成修復，形成死鎖循環。

根本原因推測：

Tampermonkey userscript 或前端在包裝/發送 tool call payload 時，可能經過了未正確轉義的 DOM/XML Parser，或者後端 FastAPI 接收時將內容以非純文字格式（如 HTML unescape/XML parser）誤解析。

Tool arguments 中的程式碼文字沒有在最底層封裝為完整的 raw string / JSON escape，導致特殊符號（<, >, &）在傳輸管線中被截斷或清洗。

建議修復方式：

前端 Tampermonkey 擷取工具呼叫參數時，確保 payload 一律走嚴格的 JSON.stringify()，避免任何 DOM 節點中介解析。

若傳輸協議包含 XML 標籤包裝（如 <tool_call>），工具的參數內文字必須使用 <![CDATA[ ... ]]> 包覆，或在序列化前將內部字元嚴格做 HTML entity escape (&lt;, &gt;, &amp;)，並由後端還原為純 raw text。