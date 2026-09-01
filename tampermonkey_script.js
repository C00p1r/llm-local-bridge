// ==UserScript==
// @name         LLM Local Bridge Agent (v4.3 - Dynamic Memory Injection)
// @namespace    https://local.bridge/
// @version      4.3
// @description  LLM Local Bridge with dynamic workspace memory snapshot injection
// @match        https://chatgpt.com/*
// @match        https://chat.openai.com/*
// @match        https://gemini.google.com/*
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

    console.log(
        '%c[LLM Local Bridge] Tampermonkey 腳本已載入 v4.3 (Memory Enabled)',
        'color:#22c55e;font-weight:bold;font-size:14px;'
    );

    const BASE_SYSTEM_PROMPT = `[SYSTEM INSTRUCTION: LOCAL ENVIRONMENT AGENT]
你是一個具備本機工作區實際操作與 GitHub 協同能力的自動化 Agent。

### 核心原則（最高優先級）
1. 主動執行，嚴禁被動：嚴禁請使用者「手動修改」、「手動執行指令」或「自行複製貼上」。所有操作必須由你主動輸出 tool_call 區塊完成。
2. 需要查看、執行、修改時：
   - 檢視目錄、檔案內容、執行測試、安裝依賴：使用 execute_command。
   - 建立、覆寫或修改檔案：使用 write_file。
   - 查詢/建立 Issue、PR、讀取遠端倉庫檔案：使用 github_action。
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

3. GitHub 操作：
\`\`\`tool_call
{
  "tool": "github_action",
  "parameters": {
    "action": "push_workspace",
    "params": {
      "repo": "owner/repo",
      "branch": "main",
      "message": "Commit message",
      "subfolder": "llm_local_bridge_copy"
    }
  }
}
\`\`\`
`;

    let sessionToken = GM_getValue('session_token', '');
    const BASE_URL = 'http://127.0.0.1:8000';
    let isExecuting = false;
    let isNewChat = true;

    GM_registerMenuCommand('🔑 設定 / 更新 Local Bridge Token', () => {
        const token = prompt('請輸入 Python 終端顯示的 Session Token:', sessionToken);
        if (token) {
            sessionToken = token.trim();
            GM_setValue('session_token', sessionToken);
            console.log('[Bridge] Session Token 已更新');
        }
    });

    function fetchContextPrompt() {
        if (!sessionToken) {
            sessionToken = GM_getValue('session_token', '');
        }

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
        if (!sessionToken) {
            sessionToken = GM_getValue('session_token', '');
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
                timeout: 35000,
                onload: (res) => {
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
                ontimeout: () => reject('執行逾時 (35s)'),
                onerror: (e) => reject(`網路錯誤: ${e}`)
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
        await new Promise((r) => setTimeout(r, 400));

        const btn = isChatGPT
            ? document.querySelector('button[data-testid="send-button"], button[aria-label="Send prompt"]')
            : document.querySelector('button.send-button, button[aria-label*="Send"], button[aria-label*="傳送"]');

        if (!btn || btn.disabled) return false;

        btn.click();
        console.log('[Bridge] 送出訊息');
        await new Promise((r) => setTimeout(r, 1200));
        return true;
    }

    function extractJSONObject(text) {
        const start = text.indexOf('{');
        if (start === -1) return null;

        let depth = 0;
        let inString = false;

        for (let i = start; i < text.length; i++) {
            const c = text[i];
            if (inString) {
                if (c === '\\') {
                    i++;
                } else if (c === '"') {
                    inString = false;
                }
                continue;
            }

            if (c === '"') {
                inString = true;
            } else if (c === '{') {
                depth++;
            } else if (c === '}') {
                depth--;
                if (depth === 0) {
                    return text.substring(start, i + 1);
                }
            }
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

            const jsonStr = extractJSONObject(text);
            if (!jsonStr) continue;

            try {
                const parsed = JSON.parse(jsonStr);
                if (!parsed.tool || !parsed.parameters) continue;

                el.dataset.bridgeExecuted = 'true';
                console.log('%c[Bridge] ✓ 偵測到 AI Tool Call', 'color:#38bdf8;font-weight:bold;', parsed.tool, parsed);
                return { parsed, element: el };
            } catch (err) {
                try {
                    const cleaned = jsonStr.replace(/\\n/g, "\\n");
                    const parsed = JSON.parse(cleaned);
                    if (parsed.tool && parsed.parameters) {
                        el.dataset.bridgeExecuted = 'true';
                        return { parsed, element: el };
                    }
                } catch (e) {}
            }
        }
        return null;
    }

    setInterval(async () => {
        if (isExecuting || isStreaming()) return;

        const target = getNextToolCall();
        if (!target) return;

        isExecuting = true;
        console.log('%c[Bridge] ▶ 開始執行 Tool', 'color:#f59e0b;font-weight:bold;', target.parsed.tool);

        try {
            const res = await sendToBackend(target.parsed);
            const reply = `[TOOL_RESULT]\n\`\`\`json\n${JSON.stringify(res, null, 2)}\n\`\`\``;
            await submitToLLM(reply);
        } catch (err) {
            console.error('[Bridge] Tool 執行失敗:', err);
            const errReply = `[TOOL_RESULT]\n\`\`\`json\n${JSON.stringify({ status: 'error', output: String(err) }, null, 2)}\n\`\`\``;
            await submitToLLM(errReply);
        } finally {
            isExecuting = false;
        }
    }, 700);

    document.addEventListener(
        'keydown',
        async (e) => {
            if (e.key !== 'Enter' || e.shiftKey || !isNewChat) return;

            const isChatGPT = location.hostname.includes('chatgpt') || location.hostname.includes('openai');
            const inputEl = isChatGPT
                ? document.querySelector('#prompt-textarea')
                : document.querySelector('.ql-editor, div[contenteditable="true"], textarea');

            if (!inputEl || document.activeElement !== inputEl) return;

            const val = inputEl.innerText || inputEl.value || '';
            if (val.trim() && !val.startsWith('[SYSTEM INSTRUCTION')) {
                e.preventDefault();
                e.stopPropagation();
                isNewChat = false;
                console.log('[Bridge] 正在取得工作區快照並注入 Prompt...');
                
                const memoryContext = await fetchContextPrompt();
                const fullPrompt = `${BASE_SYSTEM_PROMPT}\n${memoryContext}\n---\n使用者的輸入如下：\n${val.trim()}`;
                
                await submitToLLM(fullPrompt);
            }
        },
        true
    );
})();
