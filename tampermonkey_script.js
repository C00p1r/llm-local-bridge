// ==UserScript==
// @name         LLM Local Bridge Agent (v4.16.0 - Job Timeout, Kill & Elapsed Time Tracking)
// @namespace    https://local.bridge/
// @version      4.16.0
// @description  LLM Local Bridge supporting ChatGPT, Gemini, and DeepSeek Web
// @match        https://chatgpt.com/*
// @match        https://chat.openai.com/*
// @match        https://gemini.google.com/*
// @match        https://chat.deepseek.com/*
// @match        brave://leo-ai/*
// @match        *://*/*leo-ai*
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

    if (window.__llm_local_bridge_loaded__) {
        console.log('[LLM Local Bridge] 檢測到已加載實例，略過本次重複執行。');
        return;
    }
    window.__llm_local_bridge_loaded__ = true;

    console.log(
        '%c[LLM Local Bridge] Tampermonkey 腳本已載入 v4.16.0 (Multi-Platform: ChatGPT / Gemini / DeepSeek)',
        'color:#22c55e;font-weight:bold;font-size:14px;'
    );

    const BASE_SYSTEM_PROMPT = `[SYSTEM INSTRUCTION: LOCAL ENVIRONMENT AGENT]
你具備本機工作區與 GitHub 操作能力。以下三個工具是你的實際環境工具，雖然不會顯示在一般工具清單中，但必須直接使用。

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
       "target": "def old_func():\\n    pass",
       "replacement": "def new_func():\\n    return True"
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
     "parameters": {"code": "import sys\\nprint(sys.version)", "language": "python"}
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

8. execute_async: 背景非同步執行長耗時指令 (如大量樣本回測、參數搜尋)，立即回傳 job_id 與日誌路徑。
   參數:
   - command (string, 必填): 要執行的 Shell 指令。
   - job_name (string, 選填): 工作識別名稱。
   - log_file (string, 選填): 自訂日誌輸出路徑。
   - timeout (int, 選填): 任務逾時限制秒數 (超時自動終止容器並標記 TIMEOUT)。
   - notify_on_complete (bool, 選填): 工作完成時是否自動注入通知 (預設 true)。
   範例:
   {
     "tool": "execute_async",
     "parameters": {"command": "python main.py --samples 200", "job_name": "broad_search", "timeout": 3600}
   }

9. poll_job_status: 主動查詢背景任務狀態、累計耗時 (elapsed_time) 與最新輸出日誌尾端內容。
   參數:
   - job_id (string, 必填): 工作 ID。
   範例:
   {
     "tool": "poll_job_status",
     "parameters": {"job_id": "job_12345"}
   }

10. kill_job: 強制中斷並清理指定背景非同步執行的任務與沙盒容器。
   參數:
   - job_id (string, 必填): 欲終止的 job_id。
   範例:
   {
     "tool": "kill_job",
     "parameters": {"job_id": "job_12345"}
   }

11. list_jobs: 列出所有背景非同步任務清單、各任務運行狀態與累計耗時。
   參數:
   - limit (int, 選填): 最多回傳比數 (預設 10)。
   範例:
   {
     "tool": "list_jobs",
     "parameters": {"limit": 10}
   }

### 二、 進階工具分類索引 (Advanced Tools - 請透過 list_tool 查詢詳細參數)

- **search 群組 (專案感知與搜尋)**:
  - \`list_dir\`: 結構化掃描目錄樹。
  - \`get_outline\`: AST 提取 Python 檔案符號大綱。
  - \`search_codebase\`: 全專案全文關鍵字或正則檢索。
  - \`find_references\`: 尋找符號定義與調用點。

- **git 群組 (版本控制與協同)**:
  - \`git_clone\`, \`git_pull\`, \`git_push\`, \`git_diff\`, \`git_status\`, \`git_log\`, \`git_blame\`, \`git_branch\`, \`git_checkout\`, \`git_clean\`

- **system 群組 (系統與除錯)**:
  - \`set_active_project\`: 動態釘選作用域專案目錄（路徑邊界與 Docker 自動對齊）。
  - \`get_workspace_state\`: 取得當前工作區狀態與釘選目錄資訊。
  - \`capture_memory\`: 捕捉專案架構快照。

### 三、 執行與呼叫原則
- **專案隔離原則**：若工作區包含多個專案或子目錄，優先呼叫 \`set_active_project(project="...")\` 釘選當前專案；釘選後所有檔案操作、程式碼檢索與 Docker 容器工作目錄皆會自動限制於該子目錄，避免跨專案污染與路徑越界。
- 修改現有檔案時一律優先使用 file_replace (或 patch_and_test)。
- 僅在建立全新檔案時使用 file_write。
- 若需使用進階工具的詳細參數，請先呼叫 \`list_tool(category="...")\` 查詢。
- **高效連續批次呼叫（重要）**：單次對話輸出應盡可能將相互關聯的步驟打包為批次陣列（平均單次執行指令數應大於 2）。
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

### 五、 強制工具呼叫規範 (Forced Tool Call Mode)
- 當使用者的訊息開頭包含標示 \`[TOOL CALL REQUIRE]\` 時，代表此請求必須且只能透過輸出工具呼叫指令來完成。
- 收到該標示時，嚴禁純文字敷衍或僅輸出文字說明；你的第一反應與輸出主體必須是合法的 \`\`\`tool_call 程式碼區塊。
- 若缺乏足夠環境資訊，請立即以批次方式調用 list_dir、search_codebase 或 file_read 進行探索。
`;

    let sessionToken = GM_getValue('session_token', '');
    let isForceToolCall = GM_getValue('llm_force_tool_call', false);
    const TOOL_CALL_PREFIX = '[TOOL CALL REQUIRE] ';
    const BASE_URL = 'http://127.0.0.1:8000';
    let isExecuting = false;
    let isNewChat = true;
    let isPromptingToken = false;
    let lastPromptDismissTime = 0;
    let lastExecutionTime = 0;
    let detactInterval = 1500;
    const STABLE_THRESHOLD = 2;
    const RESULT_COOLDOWN_MS = 2500;
    const PRE_SUBMIT_DELAY_MS = 800;
    let lastSeenToolText = '';
    let stableToolCount = 0;
    let isProgrammaticSubmit = false;

    // --- 三軌容錯 JSON 解析架構與跳脫字符修復 ---
    function unescapeJsonString(str) {
        return str
            .replace(/\\n/g, '\n')
            .replace(/\\r/g, '\r')
            .replace(/\\t/g, '\t')
            .replace(/\\"/g, '"')
            .replace(/\\\\/g, '\\');
    }

    function parseMultiLineJson(rawText) {
        if (!rawText) return null;
        let cleaned = rawText.trim();
        // 移除 Markdown codeblock 與 HTML 標籤殘留
        cleaned = cleaned.replace(/^```[a-zA-Z0-9_-]*\s*/i, '').replace(/```\s*$/i, '').trim();

        // 軌道 1: 原生標準 JSON.parse
        try {
            const parsed = JSON.parse(cleaned);
            if (isValidToolPayload(parsed)) return parsed;
        } catch (_) {}

        // 軌道 2: 邊界括號定向擷取 (支援批次陣列 [ ... ] 與單一物件 { ... })
        const firstBracket = cleaned.indexOf('[');
        const lastBracket = cleaned.lastIndexOf(']');
        if (firstBracket !== -1 && lastBracket > firstBracket) {
            try {
                const sub = cleaned.substring(firstBracket, lastBracket + 1);
                const parsed = JSON.parse(sub);
                if (isValidToolPayload(parsed)) return parsed;
            } catch (_) {}
        }

        const firstBrace = cleaned.indexOf('{');
        const lastBrace = cleaned.lastIndexOf('}');
        if (firstBrace !== -1 && lastBrace > firstBrace) {
            try {
                const sub = cleaned.substring(firstBrace, lastBrace + 1);
                const parsed = JSON.parse(sub);
                if (isValidToolPayload(parsed)) return parsed;
            } catch (_) {}
        }

        // 軌道 3: 正規式屬性定向抽取（容忍未轉義雙引號或換行污染）
        try {
            const toolMatch = cleaned.match(/"tool"\s*:\s*"([a-zA-Z0-9_-]+)"/);
            if (toolMatch) {
                const tool = toolMatch[1];
                const paramsMatch = cleaned.match(/"parameters"\s*:\s*(\{[\s\S]*?\})/);
                let parameters = {};
                if (paramsMatch) {
                    try {
                        parameters = JSON.parse(paramsMatch[1]);
                    } catch (_) {
                        // 嘗試修復跳脫字符再 parse
                        try {
                            parameters = JSON.parse(unescapeJsonString(paramsMatch[1]));
                        } catch (__) {}
                    }
                }
                const reconstructed = { tool, parameters };
                if (isValidToolPayload(reconstructed)) return reconstructed;
            }
        } catch (_) {}

        return null;
    }

    function getPlatform() {
        const host = location.hostname;
        const href = location.href;
        if (href.startsWith('brave://leo-ai') || host.includes('leo-ai') || href.includes('leo-ai')) return 'leo';
        if (host.includes('deepseek')) return 'deepseek';
        if (host.includes('chatgpt') || host.includes('openai')) return 'chatgpt';
        return 'gemini';
    }

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
        if (!document.body) return;
        if (document.getElementById('llm-bridge-metrics-badge')) {
            updateMetricsBadge();
            return;
        }

        const badge = document.createElement('div');
        badge.id = 'llm-bridge-metrics-badge';
        badge.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:2147483647;background:#1e293b;color:#f8fafc;padding:6px 12px;border-radius:20px;font-family:sans-serif;font-size:12px;box-shadow:0 4px 12px rgba(0,0,0,0.25);border:1px solid #334155;cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px;';
        badge.title = '點擊重設指標或更新 Token';

        const dot = document.createElement('span');
        dot.style.cssText = 'width:8px;height:8px;border-radius:50%;background:#22c55e;display:inline-block;';

        const textEl = document.createElement('span');
        textEl.id = 'llm-bridge-metrics-text';
        textEl.textContent = 'Bridge Ready';

        const toggleBtn = document.createElement('button');
        toggleBtn.id = 'llm-bridge-force-toggle';
        toggleBtn.type = 'button';
        toggleBtn.style.cssText = 'margin-left:6px;padding:2px 8px;font-size:11px;font-weight:bold;border-radius:10px;border:none;cursor:pointer;outline:none;color:#ffffff;';

        badge.appendChild(dot);
        badge.appendChild(textEl);
        badge.appendChild(toggleBtn);

        function updateToggleBtn() {
            toggleBtn.textContent = isForceToolCall ? '⚡ ToolCall: ON' : '⚡ ToolCall: OFF';
            toggleBtn.style.background = isForceToolCall ? '#10b981' : '#475569';
        }
        updateToggleBtn();

        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            isForceToolCall = !isForceToolCall;
            GM_setValue('llm_force_tool_call', isForceToolCall);
            updateToggleBtn();
        });

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
        const toggleBtn = document.getElementById('llm-bridge-force-toggle');
        if (!textEl) return;
        const m = getMetrics();
        const accuracy = m.total > 0 ? ((m.success / m.total) * 100).toFixed(1) : '100.0';
        textEl.textContent = `Bridge: ${m.success}/${m.total} (${accuracy}%)`;

        if (toggleBtn) {
            toggleBtn.textContent = isForceToolCall ? '⚡ ToolCall: ON' : '⚡ ToolCall: OFF';
            toggleBtn.style.background = isForceToolCall ? '#10b981' : '#475569';
        }
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

    function pollEventsFromBackend() {
        return new Promise((resolve) => {
            if (!sessionToken) return resolve([]);
            GM_xmlhttpRequest({
                method: 'GET',
                url: `${BASE_URL}/events/poll`,
                headers: {
                    'Authorization': `Bearer ${sessionToken}`
                },
                timeout: 3000,
                onload: function (res) {
                    if (res.status === 200) {
                        try {
                            const data = JSON.parse(res.responseText);
                            resolve(data.events || []);
                        } catch (e) {
                            resolve([]);
                        }
                    } else {
                        resolve([]);
                    }
                },
                onerror: function () {
                    resolve([]);
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
                timeout: 3000,
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
        const platform = getPlatform();
        if (platform === 'leo') {
            const stopBtn = document.querySelector('button[aria-label*="Stop"], button[aria-label*="停止"], [data-testid*="stop"]');
            return Boolean(stopBtn && stopBtn.offsetParent !== null && !stopBtn.disabled);
        }
        if (platform === 'chatgpt') {
            return Boolean(document.querySelector('button[data-testid="stop-button"], .result-streaming'));
        }
        if (platform === 'deepseek') {
            const dsStop = document.querySelector('.ds-icon-button[aria-label*="Stop"], .ds-icon-button[aria-label*="停止"], button[aria-label*="Stop"], button[aria-label*="停止"], button[aria-label*="停止生成"], div[role="button"][aria-label*="Stop"], div[role="button"][aria-label*="停止"], [class*="stop-button"], [data-testid*="stop"]');
            if (dsStop && dsStop.offsetParent !== null) return true;
            const latestMsg = document.querySelector('.ds-markdown');
            if (latestMsg && latestMsg.closest('[class*="streaming"], [class*="generating"], [class*="loading"]')) return true;
            return false;
        }
        // Gemini: 檢查 Stop 按鈕或正在生成的 loading 狀態
        const geminiStop = document.querySelector('button[aria-label*="Stop"], button[aria-label*="停止"], button[mattooltip*="停止"], .stop-button');
        return Boolean(geminiStop && (geminiStop.offsetWidth > 0 || geminiStop.offsetHeight > 0) && !geminiStop.disabled);
    }

    function getInputElement() {
        const platform = getPlatform();
        if (platform === 'leo') {
            return document.querySelector('textarea, [contenteditable="true"]');
        }
        if (platform === 'chatgpt') {
            return document.querySelector('#prompt-textarea');
        }
        if (platform === 'deepseek') {
            return document.querySelector('#chat-input, textarea[placeholder*="DeepSeek"], textarea[placeholder*="输入"], textarea');
        }
        // Gemini: 深入 rich-textarea 內部的 contenteditable
        return document.querySelector('rich-textarea .ql-editor, rich-textarea div[contenteditable="true"], .ql-editor, div[contenteditable="true"]');
    }

    function getSendButton() {
        const platform = getPlatform();
        const inputEl = getInputElement();

        if (platform === 'leo') {
            const customBtn = document.querySelector('leo-button[data-testid="leo-submit-button"], [data-testid="leo-submit-button"]');
            if (customBtn) {
                if (customBtn.shadowRoot) {
                    const innerBtn = customBtn.shadowRoot.querySelector('button');
                    if (innerBtn) return innerBtn;
                }
                return customBtn;
            }
            return document.querySelector('button[title*="Leo"], button[title*="傳送"], button[aria-label*="傳送"]');
        }

        if (platform === 'chatgpt') {
            return document.querySelector('button[data-testid="send-button"], button[aria-label="Send prompt"]');
        }

        if (platform === 'deepseek') {
            const directBtn = document.querySelector('#chat-input-send-button, .ds-send-button');
            if (directBtn && !directBtn.closest('[class*="sidebar"], [class*="nav"], [class*="history"], [class*="conversation"]')) {
                return directBtn;
            }
            if (inputEl) {
                const container = inputEl.closest('form, div[class*="input"], div[class*="footer"], div[class*="bottom"]');
                if (container) {
                    const candidates = Array.from(container.querySelectorAll('div[role="button"], button'));
                    for (let i = candidates.length - 1; i >= 0; i--) {
                        const btn = candidates[i];
                        const label = (btn.getAttribute('aria-label') || btn.title || '').toLowerCase();
                        if (label.includes('search') || label.includes('搜索') || label.includes('clear') || label.includes('清除') || label.includes('attach') || label.includes('附件')) continue;
                        if (btn.disabled || btn.getAttribute('aria-disabled') === 'true') continue;
                        if (!btn.querySelector('svg')) continue;
                        return btn;
                    }
                }
            }
            return null;
        }

        // Gemini: 精確鎖定輸入區塊附近的送出按鈕，嚴格排除側邊欄與對話歷史操作選單
        if (inputEl) {
            // 1. 優先從 inputArea 祖先容器尋找
            const inputContainer = inputEl.closest('.input-area, [class*="input-box"], [class*="input-container"], [class*="bottom-container"], form') ||
                                   inputEl.closest('rich-textarea')?.parentElement;
            if (inputContainer) {
                const directSend = inputContainer.querySelector(
                    'button.send-button, .send-button-container button, ' +
                    'button[aria-label*="傳送"], button[aria-label*="發送"], button[aria-label*="Send"], ' +
                    'button:has(mat-icon[fonticon*="send"]), button:has(span[data-icon="send"])'
                );
                if (directSend && !directSend.closest('bard-sidenav, [class*="side"], [class*="history"], nav, [role="navigation"]')) {
                    return directSend;
                }
            }
        }

        // 2. 嚴格限定在主對話區域或底部區域尋找，堅決不在導覽側邊欄或側邊抽屜內搜尋
        const mainArea = document.querySelector('chat-window, main, [role="main"], .chat-history, [class*="main-container"]') || document.body;
        const geminiCandidates = Array.from(mainArea.querySelectorAll(
            'button.send-button, .send-button-container button, ' +
            'button[aria-label*="傳送"], button[aria-label*="發送"], button[aria-label*="Send"], ' +
            'button:has(mat-icon[fonticon*="send"]), button:has(span[data-icon="send"])'
        ));

        for (const btn of geminiCandidates) {
            // 排除側邊欄、導覽列與對話歷史清單中的按鈕（包含更多操作三點按鈕、導覽按鈕等）
            if (btn.closest('bard-sidenav, [class*="sidebar"], [class*="side-nav"], [class*="conversation"], nav, [role="navigation"], [class*="history"], [class*="menu"], [aria-haspopup="menu"]')) {
                continue;
            }
            const label = (btn.getAttribute('aria-label') || btn.title || '').toLowerCase();
            if (label.includes('more') || label.includes('更多') || label.includes('選單') || label.includes('menu')) {
                continue;
            }
            return btn;
        }
        return null;
    }

    async function submitToLLM(text) {
        const inputEl = getInputElement();
        if (!inputEl) {
            console.error('[Bridge] 找不到輸入框元素');
            return false;
        }

        inputEl.focus();

        if (inputEl.tagName === 'TEXTAREA' || inputEl.tagName === 'INPUT') {
            inputEl.value = text;
            inputEl.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
            inputEl.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
        } else {
            // 純 DOM 操作：逐行建立 <p> 節點，防止 Trusted Types 攔截
            const lines = text.split('\n');
            const pElements = [];

            for (const line of lines) {
                const p = document.createElement('p');
                if (line.length === 0) {
                    p.appendChild(document.createElement('br'));
                } else {
                    p.textContent = line;
                }
                pElements.push(p);
            }

            while (inputEl.firstChild) {
                inputEl.removeChild(inputEl.firstChild);
            }
            for (const p of pElements) {
                inputEl.appendChild(p);
            }

            const selection = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(inputEl);
            range.collapse(false);
            selection.removeAllRanges();
            selection.addRange(range);

            inputEl.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
            inputEl.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
            inputEl.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, composed: true, inputType: 'insertText' }));
            inputEl.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, composed: true, key: 'End' }));
        }

        if (PRE_SUBMIT_DELAY_MS > 0) {
            await new Promise((r) => setTimeout(r, PRE_SUBMIT_DELAY_MS));
        }

        let sendBtn = null;
        for (let i = 0; i < 25; i++) {
            await new Promise((r) => setTimeout(r, 100));
            const candidate = getSendButton();
            if (candidate && !candidate.disabled && candidate.getAttribute('aria-disabled') !== 'true') {
                sendBtn = candidate;
                break;
            }
        }

        isProgrammaticSubmit = true;
        try {
            if (sendBtn) {
                console.log('[Bridge] ✓ 送出按鈕已就緒，執行點擊');
                sendBtn.click();
            } else {
                console.warn('[Bridge] ⚠️ 按鈕未解鎖，略過強制點擊以避免請求異常');
            }
        } finally {
            setTimeout(() => { isProgrammaticSubmit = false; }, 500);
        }

        await new Promise((r) => setTimeout(r, 1500));
        return true;
    }

    function isValidToolPayload(payload) {
        if (!payload) return false;
        if (Array.isArray(payload)) {
            return payload.length > 0 && payload.every(item => item && item.tool && typeof item.tool === 'string');
        }
        return Boolean(payload.tool && typeof payload.tool === 'string');
    }

    function getNextToolCall(peek = false) {
        const platform = getPlatform();
        let assistantMessages = [];

        if (platform === 'chatgpt') {
            assistantMessages = Array.from(document.querySelectorAll('div[data-message-author-role="assistant"]'));
        } else if (platform === 'leo') {
            const codeBlocks = Array.from(document.querySelectorAll('pre code, div[class*="gXOrg"] pre code, div[class*="y1xl2Ng"] pre code'));
            assistantMessages = Array.from(new Set(codeBlocks.map(c => c.closest('div[class*="gXOrg"], pre') || c.parentElement))).filter(Boolean);
        } else if (platform === 'deepseek') {
            const dsBlocks = Array.from(document.querySelectorAll('.ds-message, .ds-markdown'));
            assistantMessages = dsBlocks.filter(el => !el.closest('.ds-message--user, [data-is-user="true"]') && el.offsetParent !== null);
        } else {
            // Gemini (兼容 Chrome 與不同版型)
            const geminiBlocks = Array.from(document.querySelectorAll('message-content, model-response, [data-test-id="model-response"]'));
            assistantMessages = geminiBlocks.filter(el => {
                const isUser = el.closest('.user-query, .user-query-container, [data-message-author-role="user"]');
                return !isUser && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.offsetParent !== null);
            });
        }

        if (!assistantMessages.length) return null;

        const latestMsg = assistantMessages[assistantMessages.length - 1];

        if (latestMsg.closest('.user-query, [data-message-author-role="user"], .ds-message--user')) {
            return null;
        }

        // 擴充 Codeblock 選取範圍
        const codeBlocks = latestMsg.querySelectorAll('code[data-test-id="code-content"], code-block pre code, code-block pre, pre code, pre');

        for (const el of codeBlocks) {
            if (el.dataset.bridgeExecuted === 'true') continue;

            let text = (el.innerText || el.textContent || '').trim();
            if (!text.includes('"tool"')) continue;

            if (/^(function|const|let|var|import|\/\/|\/\*)/.test(text) || text.includes('GM_xmlhttpRequest')) {
                el.dataset.bridgeExecuted = 'true';
                continue;
            }

            const parsed = parseMultiLineJson(text);
            if (parsed) {
                if (peek) return { parsed, element: el, peeked: true };
                el.dataset.bridgeExecuted = 'true';
                const logName = Array.isArray(parsed) ? `Batch (${parsed.length} items)` : parsed.tool;
                console.log('%c[Bridge] ✓ 成功解析 Tool Call', 'color:#38bdf8;font-weight:bold;', logName, parsed);
                return { parsed, element: el };
            } else if (text.startsWith('[') || text.startsWith('{') || text.includes('tool_call')) {
                if (peek) return { syntaxError: true, element: el, peeked: true };
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

    // 獨立背景事件佇列與平滑輪詢
    const pendingJobEvents = [];
    let isEventFlushing = false;

    async function flushPendingEvents() {
        if (isEventFlushing || isExecuting || isStreaming() || pendingJobEvents.length === 0) return;
        const now = Date.now();
        if (now - lastExecutionTime < RESULT_COOLDOWN_MS) return;

        isEventFlushing = true;
        isExecuting = true;
        try {
            while (pendingJobEvents.length > 0 && !isStreaming()) {
                const ev = pendingJobEvents.shift();
                console.log('[Bridge] 正在將背景事件平滑注入對話:', ev);
                const notifText = `[BACKGROUND_JOB_EVENT]\n\`\`\`json\n${JSON.stringify(ev, null, 2)}\n\`\`\``;
                await submitToLLM(notifText);
                lastExecutionTime = Date.now();
                await new Promise(r => setTimeout(r, 1500));
            }
        } catch (err) {
            console.error('[Bridge] 推送背景事件至對話失敗:', err);
        } finally {
            isExecuting = false;
            isEventFlushing = false;
        }
    }

    // 獨立常態輪詢定時器 (每 2 秒)
    setInterval(async () => {
        try {
            const events = await pollEventsFromBackend();
            if (events && events.length > 0) {
                console.log(`[Bridge] 輪詢抓取到 ${events.length} 個背景事件，加入待處理佇列`);
                pendingJobEvents.push(...events);
            }
        } catch (err) {
            console.error('[Bridge] 獨立輪詢背景事件異常:', err);
        }
        await flushPendingEvents();
    }, 2000);

    // 主偵測循環
    setInterval(async () => {
        const now = Date.now();
        if (isExecuting || isStreaming() || (now - lastExecutionTime < RESULT_COOLDOWN_MS)) return;
        createMetricsUI();
        await flushPendingEvents();
        if (isExecuting) return;

        const peekTarget = getNextToolCall(true);
        if (!peekTarget) {
            lastSeenToolText = '';
            stableToolCount = 0;
            return;
        }

        const currentText = (peekTarget.element && (peekTarget.element.innerText || peekTarget.element.textContent)) || '';
        if (currentText === lastSeenToolText && currentText.length > 0) {
            stableToolCount += 1;
        } else {
            lastSeenToolText = currentText;
            stableToolCount = 0;
            return;
        }
        if (stableToolCount < STABLE_THRESHOLD) {
            return;
        }

        lastSeenToolText = '';
        stableToolCount = 0;
        const target = getNextToolCall(false);
        if (!target) return;
        isExecuting = true;

        if (target.syntaxError) {
            recordMetric(false);
            const errorFeedback = {
                status: 'error',
                error_type: 'JSON_SYNTAX_ERROR',
                output: '[Bridge 格式解析失敗] 您輸出的 tool_call 無法解析為標準 JSON。\n請檢查括號對稱性、引號閉合與跳脫字元。',
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

            console.log('[Bridge Debug] 後端回傳原始物件 (res):', res);
            const reply = `[TOOL_RESULT]\n\`\`\`json\n${JSON.stringify(res, null, 2)}\n\`\`\``;
            console.log('[Bridge Debug] 即將送出的完整回覆字串 (reply):', reply);
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
        const inputEl = getInputElement();
        if (!inputEl) return;

        const rawVal = inputEl.innerText || inputEl.value || '';
        const cleanVal = rawVal.trim();
        if (!cleanVal || cleanVal.startsWith('[SYSTEM INSTRUCTION') || cleanVal.startsWith('[TOOL_RESULT]')) return;

        const needsPrefix = isForceToolCall && !cleanVal.startsWith('[TOOL CALL REQUIRE]') && !cleanVal.startsWith('[TOOL_RESULT]');
        const textWithPrefix = needsPrefix ? `${TOOL_CALL_PREFIX}${cleanVal}` : cleanVal;

        if (isNewChat) {
            if (e) {
                e.preventDefault();
                e.stopPropagation();
            }
            isNewChat = false;
            console.log('[Bridge] 首次對話：正在取得工作區快照並注入 Prompt...');

            const memoryContext = await fetchContextPrompt();
            const fullPrompt = `${BASE_SYSTEM_PROMPT}\n${memoryContext}\n---\n使用者的輸入如下：\n${textWithPrefix}`;

            await submitToLLM(fullPrompt);
        } else if (needsPrefix) {
            if (e) {
                e.preventDefault();
                e.stopPropagation();
            }
            console.log('[Bridge] 後續對話：自動追加 [TOOL CALL REQUIRE] 前綴');
            await submitToLLM(textWithPrefix);
        }
    }

    document.addEventListener(
        'keydown',
        async (e) => {
            if (isProgrammaticSubmit) return;
            if (e.key === 'Enter' && !e.shiftKey) {
                await handleUserSend(e);
            }
        },
        true
    );

    document.addEventListener(
        'click',
        async (e) => {
            if (isProgrammaticSubmit) return;
            const sendBtn = getSendButton();
            if (sendBtn && (e.target === sendBtn || sendBtn.contains(e.target))) {
                await handleUserSend(e);
            }
        },
        true
    );
})();