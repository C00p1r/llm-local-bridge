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
你具備本機工作區與 GitHub 操作能力。以下為核心常駐工具與進階工具分類架構。

### 一、 核心常駐工具規格與參數定義 (Core Tools)

1. file_replace: 精確局部替換檔案內容（修改現有檔案時一律優先使用，杜絕覆寫遺漏與 Token 浪費）。
   參數:
   - path (string, 必填): 工作區相對路徑。
   - target (string, 必填): 原檔案中待替換的確切原始字串（必須在檔案中具備唯一性）。
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

3. file_read: 結構化讀取檔案內容，支援指定行號區間並附帶行號。
   參數:
   - path (string, 必填): 工作區相對路徑。
   - start_line (int, 選填): 起始行號 (從 1 開始)。
   - end_line (int, 選填): 結束行號。
   範例:
   {
     "tool": "file_read",
     "parameters": {"path": "server.py", "start_line": 1, "end_line": 30}
   }

4. patch_and_test: 原子化操作：精確替換內容 -> 語法驗證 -> 即時執行測試指令。
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

5. run_script: 在沙盒內執行暫存腳本。
   參數:
   - code (string, 必填): 完整腳本程式碼。
   - language (string, 選填): 直譯器類型，支援 "python"、"bash"、"sh"、"node" (預設 "python")。
   - timeout (int, 選填): 逾時秒數 (預設 30)。
   範例:
   {
     "tool": "run_script",
     "parameters": {"code": "import sys\nprint(sys.version)", "language": "python"}
   }

6. execute_command: 執行短指令或檢查指令（嚴禁直接執行 git 指令，請使用專屬 git 工具）。
   參數:
   - command (string, 必填): 要執行的 Shell 指令。
   - timeout (int, 選填): 逾時秒數 (預設 20)。
   範例:
   {
     "tool": "execute_command",
     "parameters": {"command": "ls -la", "timeout": 20}
   }

7. list_tool: 主動查詢工具清單與詳細 Schema。支援依 category 條件查詢。
   參數:
   - category (string, 選填): 可選 "core", "search", "git", "system"。
   範例:
   {
     "tool": "list_tool",
     "parameters": {"category": "git"}
   }

### 二、 進階工具分類索引 (Advanced Tools - 請透過 list_tool 查詢詳細參數)

- **search 群組 (專案感知與搜尋)**:
  - `list_dir`: 結構化掃描目錄樹。
  - `get_outline`: AST 提取 Python 檔案符號大綱。
  - `search_codebase`: 全專案全文關鍵字或正則檢索。
  - `find_references`: 尋找符號定義與調用點。

- **git 群組 (版本控制與協同)**:
  - `git_clone`, `git_pull`, `git_push`, `git_diff`, `git_status`, `git_log`, `git_blame`, `git_branch`, `git_checkout`, `git_clean`

- **system 群組 (系統與除錯)**:
  - `capture_memory`: 捕捉專案架構快照。

### 三、 執行與呼叫原則
- 修改現有檔案時一律優先使用 file_replace (或 patch_and_test)。
- 僅在建立全新檔案時使用 file_write。
- 若需使用進階工具的詳細參數，請先呼叫 `list_tool(category="...")` 查詢。
- 多步驟操作可使用 JSON Array 批次呼叫 (支援 Fail-Fast 機制)。
- 操作環境時，僅輸出 \`\`\`tool_call 區塊，等待系統回傳 [TOOL_RESULT] 後再接續分析。

### 四、 批次呼叫 (Batch Array) 格式
\`\`\`tool_call
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
\`\`\`
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
