// ==UserScript==
// @name         LLM Local Bridge Agent (v3.2 - Stable Loop)
// @namespace    https://local.bridge/
// @version      3.2
// @description  Robust bridge with foolproof multi-turn tool calling detection
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

    const SYSTEM_PROMPT = `[SYSTEM INSTRUCTION: LOCAL ENVIRONMENT AGENT]
你現在具備本機工作區終端操作能力。

### 規則判定
1. **需要操作環境時（查閱檔案、執行指令、修改專案）：**
   嚴格且僅輸出以下格式，不要有任何前綴或解釋文字：
\`\`\`tool_call
{
  "tool": "execute_command",
  "parameters": {
    "command": "你的 bash 指令",
    "timeout": 20
  }
}
\`\`\`
2. **需要解釋、分析或回答一般問題時：**
   直接以繁體中文自然語言回覆，**絕對不要**輸出 \`\`\`tool_call 代碼區塊。
3. 輸出工具呼叫後請立即停止生成，等待系統回傳 [TOOL_RESULT]。

---
使用者的輸入如下：
`;

    let sessionToken = GM_getValue('session_token', '');
    const BASE_URL = 'http://127.0.0.1:8000';
    let isExecuting = false;
    let isNewChat = true;

    GM_registerMenuCommand('設定 / 更新 Local Bridge Token', () => {
        const token = prompt('請輸入 Python 終端顯示的 Session Token:', sessionToken);
        if (token) {
            sessionToken = token.trim();
            GM_setValue('session_token', sessionToken);
            verifyHealth();
        }
    });

    function verifyHealth() {
        if (!sessionToken) return;
        GM_xmlhttpRequest({
            method: 'GET',
            url: `${BASE_URL}/health`,
            headers: { 'Authorization': `Bearer ${sessionToken}` },
            onload: (res) => {
                if (res.status === 200) {
                    console.log('%c[Bridge] 成功連線至本機服務端！', 'color: #00ff00; font-weight: bold;');
                }
            }
        });
    }

    function sendCommand(payload) {
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
                    if (res.status === 200) {
                        try { resolve(JSON.parse(res.responseText)); }
                        catch (e) { reject('JSON Parse Error'); }
                    } else {
                        reject(`Server Error ${res.status}: ${res.responseText}`);
                    }
                },
                ontimeout: () => reject('執行逾時 (35s)'),
                onerror: (e) => reject(`網路錯誤: ${e}`)
            });
        });
    }

    // 判斷是否正在生成
    function isStreaming() {
        const isChatGPT = location.hostname.includes('chatgpt') || location.hostname.includes('openai');
        if (isChatGPT) {
            return Boolean(
                document.querySelector('button[data-testid="stop-button"]') ||
                document.querySelector('.result-streaming')
            );
        } else {
            return Boolean(
                document.querySelector('button[aria-label="Stop response"]') ||
                document.querySelector('.sparkle-animating')
            );
        }
    }

    // 自動填入並送出
    async function submitToLLM(text) {
        const isChatGPT = location.hostname.includes('chatgpt') || location.hostname.includes('openai');
        const inputEl = isChatGPT
            ? document.querySelector('#prompt-textarea')
            : document.querySelector('.ql-editor, div[contenteditable="true"]');
        if (!inputEl) return;

        if (isChatGPT) {
            if (inputEl.tagName.toLowerCase() === 'textarea') {
                inputEl.value = text;
            } else {
                inputEl.innerHTML = `<p>${text.replace(/\n/g, '<br>')}</p>`;
            }
        } else {
            inputEl.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, text);
        }
        inputEl.dispatchEvent(new Event('input', { bubbles: true }));

        // 等待 React/Vue 狀態更新
        await new Promise(r => setTimeout(r, 400));
        const btn = isChatGPT
            ? document.querySelector('button[data-testid="send-button"], button[aria-label="Send prompt"]')
            : document.querySelector('button.send-button, button[aria-label="Send message"]');

        if (btn && !btn.disabled) {
            btn.click();
            // 送出後強制等待 1.5 秒，確保網頁進入生成中狀態，防止輪詢搶先觸發
            await new Promise(r => setTimeout(r, 1500));
        }
    }

    // 首次輸入攔截注入
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && isNewChat) {
            const isChatGPT = location.hostname.includes('chatgpt') || location.hostname.includes('openai');
            const inputEl = isChatGPT ? document.querySelector('#prompt-textarea') : document.querySelector('.ql-editor, div[contenteditable="true"]');

            if (inputEl && document.activeElement === inputEl) {
                const val = inputEl.innerText || inputEl.value || '';
                if (val.trim() && !val.startsWith('[SYSTEM INSTRUCTION')) {
                    e.preventDefault();
                    e.stopPropagation();
                    isNewChat = false;
                    submitToLLM(SYSTEM_PROMPT + val.trim());
                }
            }
        }
    }, true);

    // 輔助：安全解碼與提取 JSON
    function tryExtractToolCall(rawText) {
        if (!rawText) return null;

        // 1. 去除 Markdown 標記
        let clean = rawText.replace(/```(?:tool_call|json)?/g, '').replace(/```/g, '').trim();

        // 2. 尋找最外層的 { ... }
        const firstBrace = clean.indexOf('{');
        const lastBrace = clean.lastIndexOf('}');
        if (firstBrace === -1 || lastBrace === -1 || lastBrace <= firstBrace) return null;

        clean = clean.substring(firstBrace, lastBrace + 1);

        // 3. 嘗試標準解析
        try {
            const parsed = JSON.parse(clean);
            if (parsed.tool && parsed.parameters) return parsed;
        } catch (e) {
            // 若標準解析失敗，嘗試修復常見的跳脫問題
            try {
                // 將未跳脫的 raw newline 替換
                const sanitized = clean.replace(/[\u0000-\u001F]+/g, (match) => {
                    if (match === '\n') return '\\n';
                    if (match === '\r') return '\\r';
                    if (match === '\t') return '\\t';
                    return '';
                });
                const parsed = JSON.parse(sanitized);
                if (parsed.tool && parsed.parameters) return parsed;
            } catch (e2) {
                console.warn('[Bridge] JSON 解析失敗，原始文本:', clean);
            }
        }
        return null;
    }

    function findUnprocessedToolCall() {
        const isChatGPT = location.hostname.includes('chatgpt') || location.hostname.includes('openai');
        const msgs = document.querySelectorAll(isChatGPT ? 'div[data-message-author-role="assistant"]' : 'message-content');
        if (!msgs.length) return null;

        const latestMsg = msgs[msgs.length - 1];

        // 檢查所有 code / pre 節點
        const targets = latestMsg.querySelectorAll('pre, code');
        for (let el of targets) {
            if (el.dataset.bridgeExecuted === 'true') continue;

            const parsed = tryExtractToolCall(el.innerText || el.textContent);
            if (parsed) {
                return { element: el, parsed };
            }
        }

        // 若 code 標籤未命中，檢查整則訊息文字
        if (latestMsg.dataset.bridgeExecuted !== 'true') {
            const parsed = tryExtractToolCall(latestMsg.innerText || latestMsg.textContent);
            if (parsed) {
                return { element: latestMsg, parsed };
            }
        }

        return null;
    }

    // 主輪詢迴圈
    setInterval(async () => {
        if (isExecuting) return;

        // 生成中不處理
        if (isStreaming()) return;

        const target = findUnprocessedToolCall();
        if (target) {
            isExecuting = true;
            target.element.dataset.bridgeExecuted = 'true'; // 打上實體標記
            console.log('%c[Bridge] 捕捉到新指令，發送至本機:', 'color: #00bcd4; font-weight: bold;', target.parsed);

            try {
                const res = await sendCommand(target.parsed);
                const reply = `[TOOL_RESULT]\n\`\`\`json\n${JSON.stringify(res, null, 2)}\n\`\`\``;
                await submitToLLM(reply);
            } catch (err) {
                console.error('[Bridge] 執行失敗:', err);
                const errReply = `[TOOL_RESULT]\n\`\`\`json\n{\n  "status": "error",\n  "output": "${err}"\n}\n\`\`\``;
                await submitToLLM(errReply);
            } finally {
                isExecuting = false;
            }
        }
    }, 600);

    verifyHealth();
})();