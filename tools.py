SUPPORTED_TOOLS = [
    "execute_command",
    "run_script",
    "file_read",
    "file_write",
    "file_replace",
    "patch_and_test",
    "git_clone",
    "git_pull",
    "git_push",
    "git_diff",
    "git_status",
    "git_log",
    "git_blame",
    "git_branch",
    "git_checkout",
    "git_clean",
    "list_dir",
    "get_outline",
    "search_codebase",
    "find_references",
    "capture_memory",
    "list_tool"
]

TOOL_CATALOG = {
    "core": [
        {
            "name": "execute_command",
            "description": "執行短指令與環境檢查",
            "parameters": {
                "command": {"type": "str", "required": True, "description": "要執行的 Shell 指令"},
                "timeout": {"type": "int", "required": False, "default": 30, "description": "逾時秒數"}
            }
        },
        {
            "name": "run_script",
            "description": "在沙盒內執行暫存腳本",
            "parameters": {
                "code": {"type": "str", "required": True, "description": "腳本程式碼內容"},
                "language": {"type": "str", "required": False, "default": "python", "description": "支援 python, bash/sh, javascript/node"},
                "timeout": {"type": "int", "required": False, "default": 30, "description": "逾時秒數"}
            }
        },
        {
            "name": "file_read",
            "description": "結構化讀取檔案",
            "parameters": {
                "path": {"type": "str", "required": True, "description": "檔案相對路徑"},
                "start_line": {"type": "int", "required": False, "description": "起始行號 (從 1 開始)"},
                "end_line": {"type": "int", "required": False, "description": "結束行號"}
            }
        },
        {
            "name": "file_write",
            "description": "建立新檔案或全量重構",
            "parameters": {
                "path": {"type": "str", "required": True, "description": "檔案相對路徑"},
                "content": {"type": "str", "required": True, "description": "欲寫入的檔案完整內容"}
            }
        },
        {
            "name": "file_replace",
            "description": "精確局部替換檔案內容",
            "parameters": {
                "path": {"type": "str", "required": True, "description": "檔案相對路徑"},
                "target": {"type": "str", "required": True, "description": "被替換的原始文字區塊 (需具唯一性)"},
                "replacement": {"type": "str", "required": True, "description": "替換後的新文字內容"}
            }
        },
        {
            "name": "patch_and_test",
            "description": "原子化修改與即時測試",
            "parameters": {
                "path": {"type": "str", "required": True, "description": "檔案相對路徑"},
                "target": {"type": "str", "required": True, "description": "被替換的原始文字區塊"},
                "replacement": {"type": "str", "required": True, "description": "替換後的新文字內容"},
                "test_command": {"type": "str", "required": True, "description": "修改後執行的測試指令"},
                "timeout": {"type": "int", "required": False, "default": 30, "description": "測試指令逾時秒數"},
                "auto_rollback": {"type": "bool", "required": False, "default": False, "description": "測試失敗時是否自動還原檔案"}
            }
        },
        {
            "name": "list_tool",
            "description": "核心管控入口，支援 category 條件查詢",
            "parameters": {
                "category": {"type": "str", "required": False, "default": "", "description": "指定分類 (core, search, git, system)，為空時列出全部"}
            }
        }
    ],
    "search": [
        {
            "name": "list_dir",
            "description": "結構化目錄樹掃描",
            "parameters": {
                "path": {"type": "str", "required": False, "default": "", "description": "要掃描的相對目錄路徑"},
                "max_depth": {"type": "int", "required": False, "default": 3, "description": "最大遍歷深度"}
            }
        },
        {
            "name": "get_outline",
            "description": "AST 提取 Python 檔案大綱",
            "parameters": {
                "path": {"type": "str", "required": True, "description": "Python 檔案路徑 (.py)"}
            }
        },
        {
            "name": "search_codebase",
            "description": "全專案全文關鍵字與正則檢索",
            "parameters": {
                "query": {"type": "str", "required": True, "description": "搜尋關鍵字或正則表達式"},
                "path": {"type": "str", "required": False, "default": "", "description": "限定檢索的相對目錄路徑"},
                "include_pattern": {"type": "str", "required": False, "default": "", "description": "檔案過濾 pattern (如 *.py)"},
                "max_results": {"type": "int", "required": False, "default": 50, "description": "最多回傳結果數"}
            }
        },
        {
            "name": "find_references",
            "description": "尋找符號定義與調用點",
            "parameters": {
                "symbol": {"type": "str", "required": True, "description": "欲查詢的函式、類別或變數名稱"},
                "file_type": {"type": "str", "required": False, "default": "", "description": "限定副檔名 (如 py, js, ts)"},
                "scope_dir": {"type": "str", "required": False, "default": "", "description": "搜尋範圍目錄"}
            }
        }
    ],
    "git": [
        {
            "name": "git_clone",
            "description": "複製遠端儲存庫",
            "parameters": {
                "repo_url": {"type": "str", "required": True, "description": "Git 儲存庫 URL"},
                "target_subfolder": {"type": "str", "required": False, "default": "", "description": "目標子資料夾路徑"}
            }
        },
        {
            "name": "git_pull",
            "description": "拉取遠端更新",
            "parameters": {
                "subfolder": {"type": "str", "required": False, "default": "", "description": "工作區子資料夾"},
                "remote": {"type": "str", "required": False, "default": "origin", "description": "遠端主機名稱"},
                "branch": {"type": "str", "required": False, "default": "main", "description": "分支名稱"},
                "force_reset": {"type": "bool", "required": False, "default": False, "description": "是否強制 reset --hard 至遠端"}
            }
        },
        {
            "name": "git_push",
            "description": "推送異動至 GitHub",
            "parameters": {
                "repo": {"type": "str", "required": True, "description": "目標儲存庫 (owner/repo)"},
                "branch": {"type": "str", "required": False, "default": "main", "description": "目標分支"},
                "message": {"type": "str", "required": False, "default": "Update from LLM Bridge", "description": "Commit 訊息"},
                "subfolder": {"type": "str", "required": False, "default": "", "description": "要推送的子資料夾"}
            }
        },
        {
            "name": "git_diff",
            "description": "檢視 Git diff",
            "parameters": {
                "path": {"type": "str", "required": False, "default": "", "description": "單一檔案或子目錄相對路徑 (為空比對整個工作區)"}
            }
        },
        {
            "name": "git_status",
            "description": "查詢工作區狀態",
            "parameters": {
                "subfolder": {"type": "str", "required": False, "default": "", "description": "工作區子資料夾"}
            }
        },
        {
            "name": "git_log",
            "description": "檢視 Commit 歷史",
            "parameters": {
                "subfolder": {"type": "str", "required": False, "default": "", "description": "工作區子資料夾"},
                "max_count": {"type": "int", "required": False, "default": 10, "description": "回傳最大 Commit 筆數"},
                "oneline": {"type": "bool", "required": False, "default": True, "description": "是否採用單行格式顯示"},
                "file_path": {"type": "str", "required": False, "default": "", "description": "限定特定檔案的歷史"}
            }
        },
        {
            "name": "git_blame",
            "description": "追蹤檔案行修訂紀錄",
            "parameters": {
                "file_path": {"type": "str", "required": True, "description": "檔案相對路徑"},
                "start_line": {"type": "int", "required": False, "description": "起始行號"},
                "end_line": {"type": "int", "required": False, "description": "結束行號"},
                "subfolder": {"type": "str", "required": False, "default": "", "description": "工作區子資料夾"}
            }
        },
        {
            "name": "git_branch",
            "description": "分支管理",
            "parameters": {
                "action": {"type": "str", "required": False, "default": "list", "description": "操作模式: list, checkout, create"},
                "branch_name": {"type": "str", "required": False, "default": "", "description": "分支名稱 (checkout/create 時必填)"},
                "subfolder": {"type": "str", "required": False, "default": "", "description": "工作區子資料夾"}
            }
        },
        {
            "name": "git_checkout",
            "description": "切換分支或單檔復原",
            "parameters": {
                "branch_name": {"type": "str", "required": False, "default": "", "description": "切換的目標分支名稱"},
                "create_branch": {"type": "bool", "required": False, "default": False, "description": "是否建立並切換新分支 (-b)"},
                "file_path": {"type": "str", "required": False, "default": "", "description": "若要單檔復原可指定檔案路徑"},
                "subfolder": {"type": "str", "required": False, "default": "", "description": "工作區子資料夾"}
            }
        },
        {
            "name": "git_clean",
            "description": "清理未追蹤檔案",
            "parameters": {
                "subfolder": {"type": "str", "required": False, "default": "", "description": "工作區子資料夾"},
                "dry_run": {"type": "bool", "required": False, "default": False, "description": "若為 True 僅預覽待清理檔案 (-nd)，不實際刪除"}
            }
        }
    ],
    "system": [
        {
            "name": "capture_memory",
            "description": "捕捉專案架構快照",
            "parameters": {}
        }
    ]
}