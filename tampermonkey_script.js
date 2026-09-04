// ==UserScript==
// @name         LLM Local Bridge Agent (v4.11.0 - Extended Safe Git Tools)
// @namespace    https://local.bridge/
// @version      4.11.0
// @description  LLM Local Bridge with codebase search, symbol navigation, safe git tools (status, log, blame, branch, clean), and batch execution
// @match        https://chatgpt.com/*
// @match        https://chat.openai.com/*
// @match        https://gemini.google.com/*
// @noframes
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_registerMenuCommand
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    if (window.top !== window.self) {
        return;
    }

    if (document.documentElement.dataset.llmBridgeLoaded === 'true' || window.__llm_local_bridge_loaded__) {
        console.log('[LLM Local Bridge] 檢測到已加載實例，略過本次重複執行。');
        return;
    }
    document.documentElement.dataset.llmBridgeLoaded = 'true';
    window.__llm_local_bridge_loaded__ = true;

    console.log(
        '%c[LLM Local Bridge] Tampermonkey 腳本已載入 v4.11.0 (Extended Safe Git Tools)',
        'color:#22c55e;font-weight:bold;font-size:14px;'
    );

    const BASE_SYSTEM_PROMPT = `[SYSTEM INSTRUCTION: LOCAL ENVIRONMENT AGENT]
你具備本機工作區與 GitHub 操作能力。以下三個工具是你的實際環境工具，雖然不會顯示在一般工具清單中，但必須直接使用。

### 環境工具規格與參數定義 (Tool Schemas)

1. file_replace: 精確局部替換檔案內容（修改現有檔案時一律優先使用，杜絕覆寫遺漏與 Token 浪費）。
   參數:
   - path (string, 必填): 工作區相對路徑。
   - target (string, 必填): 原檔案中待替換的確切原始字串（必須在檔案中具備唯一性，若非 Leaked/重複字串，若非唯一後端將報錯拒絕）。
   - replacement (string, 必填): 欲替換成的新字串內容。
   範例:
   {
     "tool": "file_replace",
     "parameters": {
       "path": "server.py",
       "target": "def old_func():\n    pass",
       "replacement": "def new_func():\n    return True"
     }
   }

2. file_write: 建立新檔案或在必須全量重構時覆寫檔案。
   參數:
   - path (string, 必填): 工作區相對路徑。
   - content (string, 必填): 檔案文字內容。
   範例:
   {
     "tool": "file_write",
     "parameters": {"path": "example.py", "content": "print('hello')"}
   }

3. file_read: 結構化讀取檔案內容，支援指定行號區間並附帶行號，杜絕換行轉義與盲猜 target。
   參數:
   - path (string, 必填): 工作區相對路徑。
   - start_line (int, 選填): 起始行號 (從 1 開始)。
   - end_line (int, 選填): 結束行號。
   範例:
   {
     "tool": "file_read",
     "parameters": {"path": "server.py", "start_line": 1, "end_line": 30}
   }

4. patch_and_test: 原子化操作：精確替換內容 -> 語法驗證 -> 即時執行測試指令（極致縮減對話輪次並保證驗證閉環）。
   參數:
   - path (string, 必填): 工作區相對路徑。
   - target (string, 必填): 原檔案中待替換的確切原始字串。
   - replacement (string, 必填): 欲替換成的新字串內容。
   - test_command (string, 必填): 替換成功後立即執行的測試 Shell 指令。
   - timeout (int, 選填): 測試指令逾時秒數 (預設 30)。
   - auto_rollback (bool, 選填): 若測試失敗是否自動還原檔案 (預設 false)。
   範例:
   {
     "tool": "patch_and_test",
     "parameters": {
       "path": "server.py",
       "target": "DEBUG = False",
       "replacement": "DEBUG = True",
       "test_command": "python -m pytest"
     }
   }

5. git_clone: Clone 遠端儲存庫至本機工作區。
   參數:
   - repo_url (string, 必填): Git clone 網址。
   - target_subfolder (string, 選填): clone 目的目錄名稱。
   範例:
   {
     "tool": "git_clone",
     "parameters": {"repo_url": "https://github.com/owner/repo.git", "target_subfolder": "my-repo"}
   }

6. git_pull: 自遠端分支拉取更新。
   參數:
   - branch (string, 選填): 分支名稱 (預設 "main")。
   - subfolder (string, 選填): 操作子目錄 (根目錄留空 "")。
   - force_reset (bool, 選填): 是否強制覆蓋本機異動 (預設 false)。
   範例:
   {
     "tool": "git_pull",
     "parameters": {"branch": "main", "subfolder": "", "force_reset": false}
   }

7. git_push: 推送工作區異動至 GitHub 儲存庫。
   參數:
   - repo (string, 必填): "owner/repo"。
   - branch (string, 選填): 分支名稱 (預設 "main")。
   - message (string, 選填): Commit 訊息 (預設 "Update from LLM Local Bridge")。
   - subfolder (string, 選填): 操作子目錄 (根目錄留空 "")。
   範例:
   {
     "tool": "git_push",
     "parameters": {"repo": "C00p1r/llm-local-bridge", "branch": "main", "message": "update", "subfolder": ""}
   }

8. run_script: 在沙盒內執行暫存腳本 (自動建立隔離檔並保證清理)。
   參數:
   - code (string, 必填): 完整腳本程式碼。
   - language (string, 選填): 直譯器類型，支援 "python"、"bash"、"sh"、"node" (預設 "python")。
   - timeout (int, 選填): 逾時秒數 (預設 30)。
   範例:
   {
     "tool": "run_script",
     "parameters": {"code": "import sys\nprint(sys.version)", "language": "python"}
   }

9. execute_command: 執行短指令或檢查指令（嚴禁直接執行 git 指令，請使用專屬 git 工具）。
   參數:
   - command (string, 必填): 要執行的 Shell 指令。
   - timeout (int, 選填): 逾時秒數 (預設 20)。
   範例:
   {
     "tool": "execute_command",
     "parameters": {"command": "ls -la", "timeout": 20}
   }

10. git_diff: 檢視工作區相對於 Git HEAD 的 unified diff，確保推送到 GitHub 前修改乾淨且精確。
    參數:
    - path (string, 選填): 工作區子目錄或相對路徑 (預設工作區根目錄)。
    範例:
    {
      "tool": "git_diff",
      "parameters": {}
    }

11. git_status: 查詢工作區與暫存區狀態（短格式並標記分支狀態）。
    參數:
    - subfolder (string, 選填): 操作子目錄 (預設工作區根目錄)。
    範例:
    {
      "tool": "git_status",
      "parameters": {}
    }

12. git_log: 檢視 Git 提交歷史紀錄。
    參數:
    - subfolder (string, 選填): 操作子目錄 (預設工作區根目錄)。
    - max_count (int, 選填): 取得筆數 (預設 10)。
    - oneline (bool, 選填): 是否單行簡化顯示 (預設 true)。
    - file_path (string, 選填): 特定檔案路徑。
    範例:
    {
      "tool": "git_log",
      "parameters": {"max_count": 5, "oneline": true}
    }

13. git_blame: 檢視特定檔案每行修訂紀錄與作者，精準定位變更。
    參數:
    - file_path (string, 必填): 檔案相對路徑。
    - start_line (int, 選填): 起始行號。
    - end_line (int, 選填): 結束行號。
    - subfolder (string, 選填): 操作子目錄。
    範例:
    {
      "tool": "git_blame",
      "parameters": {"file_path": "server.py", "start_line": 1, "end_line": 20}
    }

14. git_branch: 查詢分支、切換分支或建立新分支。
    參數:
    - action (string, 選填): 操作類型，支援 "list", "checkout", "create" (預設 "list")。
    - branch_name (string, 選填): 分支名稱 (checkout/create 時必填)。
    - subfolder (string, 選填): 操作子目錄。
    範例:
    {
      "tool": "git_branch",
      "parameters": {"action": "list"}
    }

15. git_clean: 清理工作區未追蹤的檔案。
    參數:
    - subfolder (string, 選填): 操作子目錄。
    - dry_run (bool, 選填): 是否僅預演列出要刪除的檔案而不實際刪除 (預設 false)。
    範例:
    {
      "tool": "git_clean",
      "parameters": {"dry_run": true}
    }

16. list_dir: 結構化掃描目錄樹，自動忽略 .git, __pycache__, node_modules, .venv 等噪音目錄，大幅節省 Token。
    參數:
    - path (string, 選填): 工作區相對目錄路徑 (留空代表根目錄)。
    - max_depth (int, 選填): 掃描深度 (預設 3)。
    範例:
    {
      "tool": "list_dir",
      "parameters": {"path": "", "max_depth": 2}
    }

17. get_outline: 基於 AST 解析 Python 檔案符號大綱（Class / Function / Method）及其所在行號，快速定位 target。
    參數:
    - path (string, 必填): Python 檔案相對路徑。
    範例:
    {
      "tool": "get_outline",
      "parameters": {"path": "server.py"}
    }

18. search_codebase: 全專案全文關鍵字或正則檢索（全域雷達），快速定位變數、API 路徑與配置項。
    參數:
    - query (string, 必填): 搜尋關鍵字或正則表達式。
    - path (string, 選填): 限定子目錄（預設根目錄）。
    - include_pattern (string, 選填): 檔案過濾（如 *.py, *.java, *.ts）。
    - max_results (int, 選填): 最大筆數（預設 50）。
    範例:
    {
      "tool": "search_codebase",
      "parameters": {"query": "run_transient_script", "include_pattern": "*.py"}
    }

19. find_references: 尋找 Symbol（類別/函式/變數）的定義處與所有呼叫點，修改前進行衝擊分析。
    參數:
    - symbol (string, 必填): 標識符名稱。
    - file_type (string, 選填): 語言副檔名（如 py, java, ts）。
    - scope_dir (string, 選填): 限制搜尋目錄。
    範例:
    {
      "tool": "find_references",
      "parameters": {"symbol": "run_transient_script"}
    }

20. list_tool: 主動查詢目前環境所支援的所有可用工具名稱清單。
    參數: 無
    範例:
    {
      "tool": "list_tool",
      "parameters": {}
    }

### 執行與呼叫原則
- 修改現有檔案時一律優先使用 file_replace (或 patch_and_test)，提供精確且唯一的上下文字串。
- 僅在建立全新檔案時使用 file_write。
- 多步驟操作可使用 JSON Array 批次呼叫 (支援 Fail-Fast 機制)。
- 操作環境時，僅輸出 \`\`\`tool_call 區塊，等待系統回傳 [TOOL_RESULT] 後再接續分析。

### 批次呼叫 (Batch Array) 格式
```tool_call
[
  {
    "tool": "file_replace",
    "parameters": {"path": "config.py", "target": "DEBUG = False", "replacement": "DEBUG = True"}
  },
  {
    "tool": "execute_command",
    "parameters": {"command": "python -m pytest", "timeout": 20}
  }
]
```
`;

    let sessionToken = GM_getValue('session_token', '');
    const BASE_URL = 'http://127.0.0.1:8000';
    let isExecuting = false;
    let isNewChat = true;
    let isPromptingToken = false;
    let lastPromptDismissTime = 0;
    let lastExecutionTime = 0;
    let detactInterval = 2000;

    function getMetrics() {
        return GM_getValue('tool_call_metrics', { total: 0, success: 0, failed: 0 });
    }

    function recordMetric(isSuccess) {
        const metrics = getMetrics();
        metrics.total += 1;
        if (isSuccess) {
            metrics.success += 1;
        } else {
            metrics.failed += 1;
        }
        GM_setValue('tool_call_metrics', metrics);
        updateMetricsBadge();
    }

    function createMetricsUI() {
        if (document.getElementById('llm-bridge-metrics-badge')) return;
        const badge = document.createElement('div');
        badge.id = 'llm-bridge-metrics-badge';
        badge.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:999999;background:#1e293b;color:#f8fafc;padding:6px 12px;border-radius:20px;font-family:sans-serif;font-size:12px;box-shadow:0 4px 12px rgba(0,0,0,0.25);border:1px solid #334155;cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px;';
        badge.title = '點擊重設指標或更新 Token';
        badge.innerHTML = `<span style="width:8px;height:8px;border-radius:50%;background:#22c55e;display:inline-block;"></span><span id="llm-bridge-metrics-text">Bridge Ready</span>`;
        badge.addEventListener('click', () => {
            const choice = prompt('請選擇操作：\n1. 更新 Session Token\n2. 重設調用計數器\n輸入序號 (1 或 2)：', '1');
            if (choice === '1') {
                const newToken = prompt('請輸入新的 Session Token:', sessionToken);
                if (newToken !== null) {
                    sessionToken = newToken.trim();
                    GM_setValue('session_token', sessionToken);
                    alert('Token 已更新');
                }
            } else if (choice === '2') {
                GM_setValue('tool_call_metrics', { total: 0, success: 0, failed: 0 });
                updateMetricsBadge();
                alert('指標已重設');
            }
        });
        document.body.appendChild(badge);
        updateMetricsBadge();
    }

    function updateMetricsBadge() {
        const textEl = document.getElementById('llm-bridge-metrics-text');
        if (!textEl) return;
        const m = getMetrics();
        const accuracy = m.total > 0 ? ((m.success / m.total) * 100).toFixed(1) : '100.0';
        textEl.textContent = `Bridge: ${m.success}/${m.total} (${accuracy}%)`;
    }

    function promptForToken() {
        const now = Date.now();
        if (isPromptingToken || now - lastPromptDismissTime < 30000) return;
        isPromptingToken = true;
        setTimeout(() => {
            const input = prompt('[LLM Local Bridge] 請輸入後端生成的 Session Token:');
            if (input) {
                sessionToken = input.trim();
                GM_setValue('session_token', sessionToken);
            } else {
                lastPromptDismissTime = Date.now();
            }
            isPromptingToken = false;
        }, 500);
    }

    GM_registerMenuCommand('設定 / 更新 Session Token', () => {
        const input = prompt('[LLM Local Bridge] 請輸入 Session Token:', sessionToken);
        if (input !== null) {
            sessionToken = input.trim();
            GM_setValue('session_token', sessionToken);
            alert('Token 已成功儲存！');
        }
    });

    function sendToBackend(payload) {
        return new Promise((resolve, reject) => {
            if (!sessionToken) {
                promptForToken();
                return reject(new Error('未提供有效的 Session Token，請於彈窗輸入'));
            }

            GM_xmlhttpRequest({
                method: 'POST',
                url: `${BASE_URL}/execute`,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${sessionToken}`
                },
                data: JSON.stringify(payload),
                timeout: 180000,
                onload: function (res) {
                    if (res.status === 401) {
                        GM_setValue('session_token', '');
                        sessionToken = '';
                        promptForToken();
                        reject(new Error('驗證失敗 (401)，Session Token 可能已失效'));
                        return;
                    }
                    try {
                        const parsed = JSON.parse(res.responseText);
                        resolve(parsed);
                    } catch (e) {
                        resolve({ status: 'raw_response', output: res.responseText });
                    }
                },
                ontimeout: function () {
                    reject(new Error('連線後端超時'));
                },
                onerror: function (err) {
                    reject(new Error('無法連線到本機後端服務 (127.0.0.1:8000)'));
                }
            });
        });
    }

    function fetchContextPrompt() {
        return new Promise((resolve) => {
            if (!sessionToken) {
                resolve('');
                return;
            }
            GM_xmlhttpRequest({
                method: 'GET',
                url: `${BASE_URL}/context_prompt`,
                headers: {
                    'Authorization': `Bearer ${sessionToken}`
                },
                timeout: 5000,
                onload: function (res) {
                    if (res.status === 200) {
                        try {
                            const data = JSON.parse(res.responseText);
                            resolve(data.prompt_injection || '');
                        } catch (e) {
                            resolve('');
                        }
                    } else {
                        resolve('');
                    }
                },
                onerror: function () {
                    resolve('');
                }
            });
        });
    }

    function isStreaming() {
        const isChatGPT = location.hostname.includes('chatgpt') || location.hostname.includes('openai');
        if (isChatGPT) {
            return Boolean(document.querySelector('button[data-testid="stop-button"], .result-streaming'));
        }
        return Boolean(document.querySelector('button[aria-label*="Stop"], button[aria-label*="停止"], .sparkle-animating, mat-progress-bar'));
    }

    async function submitToLLM(text) {
        const isChatGPT = location.hostname.includes('chatgpt') || location.hostname.includes('openai');
        const inputEl = isChatGPT
            ? document.querySelector('#prompt-textarea')
            : document.querySelector('.ql-editor, div[contenteditable="true"], textarea');

        if (!inputEl) return false;

        if (inputEl.tagName && inputEl.tagName.toLowerCase() === 'textarea') {
            const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
            if (setter) {
                setter.call(inputEl, text);
            } else {
                inputEl.value = text;
            }
        } else {
            inputEl.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, text);
        }

        inputEl.dispatchEvent(new Event('input', { bubbles: true }));
        await new Promise((r) => setTimeout(r, 500));

        const btn = isChatGPT
            ? document.querySelector('button[data-testid="send-button"], button[aria-label="Send prompt"]')
            : document.querySelector('button.send-button, button[aria-label*="Send"], button[aria-label*="傳送"]');

        if (!btn || btn.disabled) return false;

        btn.click();
        console.log('[Bridge] 送出訊息');
        await new Promise((r) => setTimeout(r, 1500));
        return true;
    }

    function parseMultiLineJson(rawText) {
        const blockMatch = rawText.match(/```(?:tool_call|bridge):([a-zA-Z0-9_-]+)\s*\n([\s\S]*?)\n```/);
        if (blockMatch) {
            const action = blockMatch[1];
            const rawBody = blockMatch[2].trim();
            if (action === 'execute_command') {
                return { tool: 'execute_command', parameters: { command: rawBody } };
            }
            if (action === 'file_write' || action === 'write_file') {
                const firstNewline = rawBody.indexOf('\n');
                const path = rawBody.substring(0, firstNewline).replace(/^path:\s*/i, '').trim();
                const content = rawBody.substring(firstNewline + 1);
                return { tool: 'file_write', parameters: { path, content } };
            }
            if (action === 'run_script') {
                return { tool: 'run_script', parameters: { code: rawBody, language: 'python' } };
            }
        }

        try {
            const parsed = JSON.parse(rawText.trim());
            if (isValidToolPayload(parsed)) return parsed;
        } catch (e) {}

        const firstBracket = rawText.indexOf('[');
        const lastBracket = rawText.lastIndexOf(']');
        const firstBrace = rawText.indexOf('{');
        const lastBrace = rawText.lastIndexOf('}');

        if (firstBracket !== -1 && lastBracket !== -1 && lastBracket > firstBracket) {
            const candidateArr = rawText.substring(firstBracket, lastBracket + 1);
            try {
                const parsedArr = JSON.parse(candidateArr);
                if (isValidToolPayload(parsedArr)) return parsedArr;
            } catch (e) {}
        }

        if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
            const candidateObj = rawText.substring(firstBrace, lastBrace + 1);
            try {
                const parsedObj = JSON.parse(candidateObj);
                if (isValidToolPayload(parsedObj)) return parsedObj;
            } catch (e) {}

            try {
                const sanitized = candidateObj.replace(/"(?:[^"\\]|\\.)*"/gs, (match) => {
                    return match.replace(/\r/g, '\\r').replace(/\n/g, '\\n').replace(/\t/g, '\\t');
                });
                const parsedSanitized = JSON.parse(sanitized);
                if (isValidToolPayload(parsedSanitized)) return parsedSanitized;
            } catch (e) {}
        }

        return null;
    }

    function isValidToolPayload(payload) {
        if (!payload) return false;
        if (Array.isArray(payload)) {
            return payload.length > 0 && payload.every(item => item && item.tool && typeof item.tool === 'string');
        }
        return Boolean(payload.tool && typeof payload.tool === 'string');
    }

    function getNextToolCall() {
        const isChatGPT = location.hostname.includes('chatgpt') || location.hostname.includes('openai');
        let assistantMessages = [];
        if (isChatGPT) {
            assistantMessages = document.querySelectorAll('div[data-message-author-role="assistant"]');
        } else {
            const allModels = document.querySelectorAll('model-response, .model-response-text');
            assistantMessages = allModels.length ? allModels : document.querySelectorAll('message-content');
        }

        if (!assistantMessages.length) return null;
        const latestMsg = assistantMessages[assistantMessages.length - 1];

        if (latestMsg.closest('.user-query, [data-message-author-role="user"]')) {
            return null;
        }

        const codeBlocks = latestMsg.querySelectorAll('pre code, pre');

        for (const el of codeBlocks) {
            if (el.dataset.bridgeExecuted === 'true') continue;

            const text = (el.innerText || el.textContent || '').trim();
            if (!text.includes('"tool"')) continue;

            const parsed = parseMultiLineJson(text);
            if (parsed) {
                el.dataset.bridgeExecuted = 'true';
                const logName = Array.isArray(parsed) ? `Batch (${parsed.length} items)` : parsed.tool;
                console.log('%c[Bridge] ✓ 成功解析 Tool Call', 'color:#38bdf8;font-weight:bold;', logName, parsed);
                return { parsed, element: el };
            } else {
                // 偵測到意圖呼叫 tool 但 JSON 語法損壞，觸發即時語法反饋
                el.dataset.bridgeExecuted = 'true';
                console.warn('[Bridge] ⚠️ 偵測到損壞的 Tool Call JSON 語法');
                return {
                    syntaxError: true,
                    element: el,
                    rawSnippet: text.length > 300 ? text.substring(0, 300) + '...' : text
                };
            }
        }
        return null;
    }

    setInterval(async () => {
        const now = Date.now();
        if (isExecuting || isStreaming() || (now - lastExecutionTime < 1800)) return;
        createMetricsUI();

        const target = getNextToolCall();
        if (!target) return;

        isExecuting = true;

        if (target.syntaxError) {
            recordMetric(false);
            const errorFeedback = {
                status: 'error',
                error_type: 'JSON_SYNTAX_ERROR',
                output: '[Bridge 格式解析失敗] 您輸出的 tool_call 無法解析為標準 JSON。\n請檢查括號對稱性（例如勿輸出 [{]} 或 [{]]）、引號閉合與跳脫字元。\n\n標準範例:\n```tool_call\n[\n  {\n    "tool": "file_read",\n    "parameters": {"path": "example.py"}\n  }\n]\n```',
                raw_received: target.rawSnippet,
                exit_code: -1
            };
            const errReply = `[TOOL_RESULT]\n\`\`\`json\n${JSON.stringify(errorFeedback, null, 2)}\n\`\`\``;
            await submitToLLM(errReply);
            lastExecutionTime = Date.now();
            isExecuting = false;
            return;
        }

        const logName = Array.isArray(target.parsed) ? `Batch (${target.parsed.length} steps)` : target.parsed.tool;
        console.log('%c[Bridge] ▶ 開始執行 Tool', 'color:#f59e0b;font-weight:bold;', logName);

        try {
            const res = await sendToBackend(target.parsed);
            const isSuccess = (res && (res.status === 'success' || res.status === 'ok'));
            recordMetric(isSuccess);

            const reply = `[TOOL_RESULT]\n\`\`\`json\n${JSON.stringify(res, null, 2)}\n\`\`\``;
            await submitToLLM(reply);
        } catch (err) {
            console.error('[Bridge] Tool 執行失敗:', err);
            recordMetric(false);
            const errReply = `[TOOL_RESULT]\n\`\`\`json\n${JSON.stringify({ status: 'error', output: String(err) }, null, 2)}\n\`\`\``;
            await submitToLLM(errReply);
        } finally {
            lastExecutionTime = Date.now();
            isExecuting = false;
        }
    }, detactInterval);

    async function handleUserSend(e) {
        if (!isNewChat) return;

        const isChatGPT = location.hostname.includes('chatgpt') || location.hostname.includes('openai');
        const inputEl = isChatGPT
            ? document.querySelector('#prompt-textarea')
            : document.querySelector('.ql-editor, div[contenteditable="true"], textarea');

        if (!inputEl) return;

        const val = inputEl.innerText || inputEl.value || '';
        if (val.trim() && !val.startsWith('[SYSTEM INSTRUCTION')) {
            if (e) {
                e.preventDefault();
                e.stopPropagation();
            }
            isNewChat = false;
            console.log('[Bridge] 正在取得工作區快照並注入 Prompt...');

            const memoryContext = await fetchContextPrompt();
            const fullPrompt = `${BASE_SYSTEM_PROMPT}\n${memoryContext}\n---\n使用者的輸入如下：\n${val.trim()}`;

            await submitToLLM(fullPrompt);
        }
    }

    document.addEventListener(
        'keydown',
        async (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                await handleUserSend(e);
            }
        },
        true
    );

    document.addEventListener(
        'click',
        async (e) => {
            const target = e.target.closest('button[data-testid="send-button"], button[aria-label="Send prompt"], button.send-button, button[aria-label*="Send"], button[aria-label*="傳送"]');
            if (target) {
                await handleUserSend(e);
            }
        },
        true
    );
})();
