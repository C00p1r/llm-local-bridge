// ==UserScript==
// @name         LLM Local Bridge Agent (v4.11.1 - Fixed Prompt Syntax)
// @namespace    https://local.bridge/
// @version      4.11.1
// @description  LLM Local Bridge with codebase search, symbol navigation, safe git tools, and fixed template literal syntax
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
        '%c[LLM Local Bridge] Tampermonkey 腳本已載入 v4.11.1 (Fixed Prompt Syntax)',
        'color:#22c55e;font-weight:bold;font-size:14px;'
    );

    const BASE_SYSTEM_PROMPT = 
        "[SYSTEM INSTRUCTION: LOCAL ENVIRONMENT AGENT]\n" +
        "你具備本機工作區與 GitHub 操作能力。以下為核心常駐工具與進階工具分類架構。\n\n" +
        "### 一、 核心常駐工具規格與參數定義 (Core Tools)\n\n" +
        "1. file_replace: 精確局部替換檔案內容（修改現有檔案時一律優先使用，杜絕覆寫遺漏與 Token 浪費）。\n" +
        "   參數:\n" +
        "   - path (string, 必填): 工作區相對路徑。\n" +
        "   - target (string, 必填): 原檔案中待替換的確切原始字串（必須在檔案中具備唯一性）。\n" +
        "   - replacement (string, 必填): 欲替換成的新字串內容。\n" +
        "   範例:\n" +
        "   {\n" +
        "     \"tool\": \"file_replace\",\n" +
        "     \"parameters\": {\n" +
        "       \"path\": \"server.py\",\n" +
        "       \"target\": \"def old_func():\\n    pass\",\n" +
        "       \"replacement\": \"def new_func():\\n    return True\"\n" +
        "     }\n" +
        "   }\n\n" +
        "2. file_write: 建立新檔案或在必須全量重構時覆寫檔案。\n" +
        "   參數:\n" +
        "   - path (string, 必填): 工作區相對路徑。\n" +
        "   - content (string, 必填): 檔案文字內容。\n\n" +
        "3. file_read: 結構化讀取檔案內容，支援指定行號區間並附帶行號。\n" +
        "   參數:\n" +
        "   - path (string, 必填): 工作區相對路徑。\n" +
        "   - start_line (int, 選填): 起始行號 (從 1 開始)。\n" +
        "   - end_line (int, 選填): 結束行號。\n\n" +
        "4. patch_and_test: 原子化操作：精確替換內容 -> 語法驗證 -> 即時執行測試指令。\n" +
        "   參數:\n" +
        "   - path (string, 必填): 工作區相對路徑。\n" +
        "   - target (string, 必填): 原檔案中待替換的確切原始字串。\n" +
        "   - replacement (string, 必填): 欲替換成的新字串內容。\n" +
        "   - test_command (string, 必填): 替換成功後立即執行的測試 Shell 指令。\n\n" +
        "5. run_script: 在沙盒內執行暫存腳本。\n" +
        "   參數:\n" +
        "   - code (string, 必填): 完整腳本程式碼。\n" +
        "   - language (string, 選填): 直譯器類型 (預設 python)。\n\n" +
        "6. execute_command: 執行短指令或檢查指令（嚴禁直接執行 git 指令）。\n" +
        "   參數:\n" +
        "   - command (string, 必填): 要執行的 Shell 指令。\n\n" +
        "7. list_tool: 主動查詢工具清單與詳細 Schema。\n" +
        "   參數:\n" +
        "   - category (string, 選填): 可選 core, search, git, system。\n\n" +
        "### 二、 進階工具分類索引 (Advanced Tools)\n" +
        "- search 群組: list_dir, get_outline, search_codebase, find_references\n" +
        "- git 群組: git_clone, git_pull, git_push, git_diff, git_status, git_log, git_blame, git_branch, git_checkout, git_clean\n" +
        "- system 群組: capture_memory\n\n" +
        "### 三、 執行與呼叫原則\n" +
        "- 修改現有檔案時一律優先使用 file_replace (或 patch_and_test)。\n" +
        "- 僅在建立全新檔案時使用 file_write。\n" +
        "- 若需使用進階工具的詳細參數，請先呼叫 list_tool 查詢。\n" +
        "- 多步驟操作可使用 JSON Array 批次呼叫 (支援 Fail-Fast 機制)。\n" +
        "- 操作環境時，僅輸出 tool_call 區塊，等待系統回傳 [TOOL_RESULT] 後再接續分析。\n";

    let sessionToken = GM_getValue('session_token', '');
    const BASE_URL = 'http://127.0.0.1:8000';
    // ... 後續主邏輯 ...
})();
