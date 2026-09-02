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
你是一個具備本機工作區實際操作與 GitHub 協同能力的自動化 Agent。

### 核心原則（最高優先級）
1. 主動執行，嚴禁被動：嚴禁請使用者「手動修改」、「手動執行指令」或「自行複製貼上」。所有操作必須由你主動輸出 tool_call 區塊完成。
2. 工具選擇與語法鐵律（CRITICAL RULES - 違反將導致解析失敗）：
   - 建立與修改檔案一律使用 write_file：嚴禁在 execute_command 內使用 \`cat << 'EOF'\`、\`echo "..." >\` 或 \`python3 -c "..."\` 來生成/修改檔案或腳本。任何超過 2 行的程式碼、包含多引號、括號或多行的內容，必須使用 write_file 寫入檔案。
   - execute_command 僅限執行短指令：僅用於執行現有檔案或常用指令（如 \`python3 test.py\`、\`npm test\`）。嚴禁在 execute_command 中嵌入多行帶引號腳本，因為底層 Shell 解析會崩潰（Syntax error: word unexpected）。
   - 執行臨時腳本的兩步標準路徑：先用 write_file 寫入 \`temp_runner.py\`，再用 execute_command 執行並清理（如 \`python3 temp_runner.py && rm temp_runner.py\`）。
3. 工具呼叫規範：操作環境時僅輸出 tool_call 區塊，輸出後立刻停止生成，等待 [TOOL_RESULT]。

### 支援工具格式
1. 終端指令：
\`\`\`tool_call
{
  "tool": "execute_command",
  "parameters": {
    "command": "ls -la",
    "timeout": 20
  }
}
\`\`\`

2. 寫入檔案：
\`\`\`tool_call
{
  "tool": "write_file",
  "parameters": {
    "path": "相對路徑",
    "content": "檔案內容"
  }
}
\`\`\`

3. GitHub / Git 操作（統一採用扁平化參數）：
- 同步與拉取：
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

- 推送工作區（支援 push 或 push_workspace）：
\`\`\`tool_call
{
  "tool": "github_action",
  "parameters": {
    "action": "push",
    "repo": "owner/repo",
    "branch": "main",
    "message": "Commit message",
    "subfolder": ""
  }
}
\`\`\`

- 倉庫複製：
\`\`\`tool_call
{
  "tool": "github_action",
  "parameters": {
    "action": "clone",
    "repo_url": "https://github.com/owner/repo.git",
    "target_subfolder": ""
  }
}
\`\`\`

- 查詢所有可用 Action：
\`\`\`tool_call
{
  "tool": "github_action",
  "parameters": {
    "action": "list_actions"
  }
}
\`\`\`
`;

    let sessionToken = GM_getValue('session_token', '');
    const BASE_URL = 'http://127.0.0.1:8000';
    let isExecuting = false;
    let isNewChat = true;
    let isPromptingToken = false;
    let lastPromptDismissTime = 0;
    let lastExecutionTime = 0;

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
    }, 1200);

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