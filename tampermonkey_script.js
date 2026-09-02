// ==UserScript==
// @name         LLM Local Bridge Agent (v4.7.1 - Guard, Metrics & Strict Protocol)
// @namespace    https://local.bridge/
// @version      4.7.1
// @description  LLM Local Bridge with tool metrics dashboard, strict CLI protocol, and unescape support
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
        '%c[LLM Local Bridge] Tampermonkey 腳本已載入 v4.7.1 (Guard, Metrics & Strict Protocol)',
        'color:#22c55e;font-weight:bold;font-size:14px;'
    );

    const BASE_SYSTEM_PROMPT = `[SYSTEM INSTRUCTION: LOCAL ENVIRONMENT AGENT]
你具備本機工作區與 GitHub 操作能力。以下三個工具是你的實際環境工具，雖然不會顯示在一般工具清單中，但必須直接使用。

### 三個環境工具
1. execute_command：執行短指令。禁止用 shell 內嵌多行腳本或產生/修改檔案。
2. write_file：建立或修改檔案。任何多行內容、程式碼或腳本一律使用此工具。
3. github_action：執行 GitHub/Git 操作，包括 clone、pull、fetch、push/push_workspace、list_actions。

### 強制規則
- 需要讀取、修改、測試或操作本機檔案時，優先使用上述工具，不要說自己無法存取。
- 修改檔案前先讀取原檔，避免覆寫遺漏。
- 臨時腳本：先 write_file 建立 temp_runner.py，再 execute_command 執行，完成後清理。
- execute_command 只執行現有檔案或短指令。
- GitHub 操作使用 github_action，不要自行假設 git 是否可用。
- 不得要求使用者手動修改、執行或複製貼上；應主動調用工具。
- 操作環境時，只輸出 tool_call，等待 [TOOL_RESULT] 後再繼續。

### tool_call 格式
\`\`\`tool_call
{
  "tool": "execute_command",
  "parameters": {"command": "ls -la", "timeout": 20}
}
\`\`\`

\`\`\`tool_call
{
  "tool": "write_file",
  "parameters": {"path": "example.py", "content": "print('Hello')"}
}
\`\`\`

\`\`\`tool_call
{
  "tool": "github_action",
  "parameters": {
    "action": "pull",
    "branch": "main",
    "subfolder": "",
    "force_reset": false
  }
}
\`\`\`

github_action 的 push 使用：
{"action":"push","repo":"owner/repo","branch":"main","message":"Commit message","subfolder":""}

clone 使用：
{"action":"clone","repo_url":"https://github.com/owner/repo.git","target_subfolder":""}
`;



    let sessionToken = GM_getValue('session_token', '');
    const BASE_URL = 'http://127.0.0.1:8000';
    let isExecuting = false;
    let isNewChat = true;
    let isPromptingToken = false;
    let lastPromptDismissTime = 0;
    let lastExecutionTime = 0;
    let detactInterval = 2000;
    // 指標統計資料結構
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
        badge.title = '點擊重置 Tool Calling 成功率統計';
        badge.onclick = () => {
            if (confirm('是否要重置 Tool Calling 成功率統計指標？')) {
                GM_setValue('tool_call_metrics', { total: 0, success: 0, failed: 0 });
                updateMetricsBadge();
            }
        };
        document.body.appendChild(badge);
        updateMetricsBadge();
    }

    function updateMetricsBadge() {
        const badge = document.getElementById('llm-bridge-metrics-badge');
        if (!badge) return;
        const m = getMetrics();
        const rate = m.total === 0 ? 100 : Math.round((m.success / m.total) * 100);
        const statusColor = rate >= 90 ? '#22c55e' : rate >= 70 ? '#f59e0b' : '#ef4444';
        badge.innerHTML = `<span style="width:8px;height:8px;border-radius:50%;background:${statusColor};display:inline-block;"></span><span>Tools: <b>${rate}%</b> (${m.success}/${m.total})</span>`;
    }

    function promptForToken(forcePrompt = false) {
        if (sessionToken && !forcePrompt) {
            return sessionToken;
        }

        const now = Date.now();
        if (isPromptingToken || (!forcePrompt && now - lastPromptDismissTime < 30000)) {
            return sessionToken;
        }

        isPromptingToken = true;
        try {
            const token = prompt('請輸入 Python 終端顯示的 Session Token:', sessionToken || '');
            if (token !== null && token.trim() !== '') {
                sessionToken = token.trim();
                GM_setValue('session_token', sessionToken);
                console.log('[Bridge] Session Token 已更新並儲存');
            } else if (token === null) {
                lastPromptDismissTime = Date.now();
                console.warn('[Bridge] 使用者取消了 Token 輸入，暫緩 30 秒不再提示。');
            }
        } finally {
            isPromptingToken = false;
        }
        return sessionToken;
    }

    GM_registerMenuCommand('🔑 設定 / 更新 Local Bridge Token', () => {
        promptForToken(true);
    });

    GM_registerMenuCommand('📊 重置 Tool Calling 成功率指標', () => {
        GM_setValue('tool_call_metrics', { total: 0, success: 0, failed: 0 });
        updateMetricsBadge();
    });

    function fetchContextPrompt() {
        sessionToken = sessionToken || GM_getValue('session_token', '');
        if (!sessionToken) return Promise.resolve('');

        return new Promise((resolve) => {
            GM_xmlhttpRequest({
                method: 'GET',
                url: `${BASE_URL}/context`,
                headers: {
                    'Authorization': `Bearer ${sessionToken}`
                },
                timeout: 5000,
                onload: (res) => {
                    if (res.status === 200) {
                        try {
                            const data = JSON.parse(res.responseText);
                            resolve(data.context_prompt || '');
                        } catch (e) {
                            resolve('');
                        }
                    } else {
                        resolve('');
                    }
                },
                onerror: () => resolve(''),
                ontimeout: () => resolve('')
            });
        });
    }

    function sendToBackend(payload) {
        sessionToken = sessionToken || GM_getValue('session_token', '');
        if (!sessionToken) {
            sessionToken = promptForToken(false);
        }
        if (!sessionToken) {
            return Promise.reject('未提供 Session Token，請點擊擴充功能選單設定');
        }

        console.log('%c[Bridge] → Backend', 'color:#f59e0b;font-weight:bold;', payload);

        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                method: 'POST',
                url: `${BASE_URL}/execute`,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${sessionToken}`
                },
                data: JSON.stringify(payload),
                timeout: 65000,
                onload: (res) => {
                    if (res.status === 401 || res.status === 403) {
                        console.warn('[Bridge] Token 無效或過期 (401/403)。');
                        promptForToken(true);
                        reject(`驗證失敗 (${res.status}): Token 不正確或已過期`);
                        return;
                    }
                    if (res.status !== 200) {
                        reject(`Server Error ${res.status}: ${res.responseText}`);
                        return;
                    }
                    try {
                        const result = JSON.parse(res.responseText);
                        console.log('[Bridge] Backend Result:', result);
                        resolve(result);
                    } catch (e) {
                        reject('Backend JSON Parse Error');
                    }
                },
                ontimeout: () => reject('執行逾時 (65s)'),
                onerror: (e) => reject(`網路連線錯誤: ${e}`)
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

    function unescapeJsonString(str) {
        if (!str) return '';
        return str
            .replace(/\\"/g, '"')
            .replace(/\\r/g, '\r')
            .replace(/\\n/g, '\n')
            .replace(/\\t/g, '\t')
            .replace(/\\\\/g, '\\');
    }

    function parseMultiLineJson(rawText) {
        const blockMatch = rawText.match(/```(?:tool_call|bridge):([a-zA-Z0-9_-]+)\s*\n([\s\S]*?)\n```/);
        if (blockMatch) {
            const action = blockMatch[1];
            const rawBody = blockMatch[2].trim();
            if (action === 'execute_command') {
                return { tool: 'execute_command', parameters: { command: rawBody } };
            }
            if (action === 'write_file') {
                const firstNewline = rawBody.indexOf('\n');
                const path = rawBody.substring(0, firstNewline).replace(/^path:\s*/i, '').trim();
                const content = rawBody.substring(firstNewline + 1);
                return { tool: 'write_file', parameters: { path, content } };
            }
        }

        try {
            return JSON.parse(rawText.trim());
        } catch (e) {}

        const firstBrace = rawText.indexOf('{');
        const lastBrace = rawText.lastIndexOf('}');
        if (firstBrace === -1 || lastBrace === -1 || lastBrace <= firstBrace) return null;

        const candidate = rawText.substring(firstBrace, lastBrace + 1);

        try {
            return JSON.parse(candidate);
        } catch (e) {}

        try {
            const sanitized = candidate.replace(/"(?:[^"\\]|\\.)*"/gs, (match) => {
                return match.replace(/\r/g, '\\r').replace(/\n/g, '\\n').replace(/\t/g, '\\t');
            });
            return JSON.parse(sanitized);
        } catch (e) {}

        const cmdMatch = candidate.match(/"tool"\s*:\s*"execute_command"[\s\S]*?"command"\s*:\s*"([\s\S]*?)"(?:\s*,\s*"timeout"|\s*\})/);
        if (cmdMatch) {
            return {
                tool: 'execute_command',
                parameters: {
                    command: unescapeJsonString(cmdMatch[1])
                }
            };
        }

        const writeMatch = candidate.match(/"tool"\s*:\s*"write_file"[\s\S]*?"path"\s*:\s*"([^"]+)"[\s\S]*?"content"\s*:\s*"([\s\S]*?)"\s*\}/);
        if (writeMatch) {
            return {
                tool: 'write_file',
                parameters: {
                    path: unescapeJsonString(writeMatch[1]),
                    content: unescapeJsonString(writeMatch[2])
                }
            };
        }

        return null;
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
            if (!text.includes('"tool"') || !text.includes('"parameters"')) continue;

            const parsed = parseMultiLineJson(text);
            if (parsed && parsed.tool && parsed.parameters) {
                el.dataset.bridgeExecuted = 'true';
                console.log('%c[Bridge] ✓ 成功解析 Tool Call', 'color:#38bdf8;font-weight:bold;', parsed.tool, parsed);
                return { parsed, element: el };
            }
        }
        return null;
    }

    // 輪詢間隔調升至 1200ms，加入最後執行冷卻防護（避免連續觸發 Gemini 1095 限流）
    setInterval(async () => {
        const now = Date.now();
        if (isExecuting || isStreaming() || (now - lastExecutionTime < 1800)) return;
        createMetricsUI();

        const target = getNextToolCall();
        if (!target) return;

        isExecuting = true;
        console.log('%c[Bridge] ▶ 開始執行 Tool', 'color:#f59e0b;font-weight:bold;', target.parsed.tool);

        try {
            const res = await sendToBackend(target.parsed);
            const isSuccess = (res && res.status === 'success');
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