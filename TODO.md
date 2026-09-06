# LLM Local Bridge - 開發進度與需求追蹤 (TODO)

## 循環開發工作原則
- **流程閉環**：Agent 修改 -> Push to GitHub -> 停下等待 -> 執行端 Pull 部署 -> 驗證測試 -> 回饋日誌/需求 -> Agent 修正。
- **先讀後改**：修改前必先使用 `file_read` 確認原檔上下文，禁止通篇覆寫與盲猜。
- **遠端同步停步**：Push 至 GitHub 後立即停下回報，嚴禁跨步預設執行端狀態。
- **如實追蹤錯誤**：執行端報錯、異常與權限問題逐字記錄分析，不隱瞞。

---

## 需求清單與進度

### [Phase 4: 錯誤反饋反射機制與工具鏈正規化 (Completed)]
- [x] **1. JSON 格式損壞快速反饋 (Syntax Error Reflection)**
  - **實作**：Tampermonkey 偵測到含 `"tool"` 但無法解析之字串時，不強行猜測，直接回報 `JSON_SYNTAX_ERROR` 並附帶標準格式範例引導自我修正。
- [x] **2. 未知工具呼叫反射 (Tool Not Found Reflection)**
  - **實作**：`server.py` 在遇到未知工具名稱時，透過 `difflib` 列出最接近的建議工具名稱，並附帶完整的 `SUPPORTED_TOOLS` 清單。
- [x] **3. `execute_command` 禁止 Git 指令攔截與導引**
  - **實作**：`server.py` 攔截 `execute_command` 中的 `git ` 指令，提示改用專屬 Git 工具。
- [x] **4. 複合工具 `patch_and_test` 實作**
  - **實作**：在 `executor.py` 與 `server.py` 完成原子化 `patch_and_test` 封裝，並同步更新 `tampermonkey_script.js` 系統提示詞。
- [x] **5. Git 操作扁平化 (`git_clone` / `git_pull` / `git_push`)**
  - **實作**：將原本巢狀的 `github_action` 拆解為一級工具，並保留 `github_action` 向下相容。
- [x] **6. 檔案操作規範化命名與移除舊版相容 (`file_read` / `file_replace` / `file_write`)**
  - **實作**：在 `server.py` 與 `tampermonkey_script.js` 全面移除舊別名（`read_file`, `write_file`, `replace_content`, `github_action`），統一 15 個標準工具規範化命名。

### [Phase 5: 工具自省與全功能 Git 擴展 (In Progress)]
- [x] **1. 實作 `list_tool` 工具**
  - **實作**：在 `server.py` 註冊 `list_tool` 並同步更新 `tampermonkey_script.js` 提示詞，支援 LLM 主動查詢可用工具清單。
- [ ] **2. 完整 Git 功能擴展與實作**
  - **Init / Clone**
    - [x] `git clone` (已具備 `git_clone`)
    - [ ] `git init` ⚠️ [危險指令 - 易覆蓋/錯置儲存庫環境，暫不開放]
    - [ ] 移除 Git 倉庫 (`rm -rf .git`) ⚠️ [高危破壞性指令 - 禁止開放]
  - **Remote 遠端操作**
    - [ ] `git remote -v` (查詢遠端連結)
    - [ ] `git remote add <name> <url>` ⚠️ [危險指令 - 涉及敏感遠端覆蓋，暫不開放]
    - [ ] `git remote set-url <name> <url>` ⚠️ [危險指令 - 涉及敏感遠端覆蓋，暫不開放]
    - [ ] `git remote remove <name>` ⚠️ [危險指令 - 易造成斷連風險，暫不開放]
    - [ ] `git push -u <remote> <branch>` (推送並追蹤分支)
  - **基本版更 (Status / Add / Commit / Pull / Push)**
    - [x] `git pull` (已具備 `git_pull`，含 `--force_reset`)
    - [x] `git push` (已具備 `git_push` GitHub API 推送)
    - [x] `git status` (查詢當前工作區狀態，已具備 `git_status`)
    - [ ] `git add <file>` / `git add .` (暫存檔案)
    - [ ] `git commit -m <msg>` (本機 Commit)
    - [ ] `git restore --staged <file>` (取消暫存)
    - [ ] `git pull --rebase` ⚠️ [高危指令 - 易發生非預期衝突與歷史變更，暫不開放]
  - **檔案復原與清理**
    - [x] `git clean -fd` (清除未追蹤檔案，已具備 `git_clean`，支援 `--dry_run`)
    - [x] `git restore <file>` / `git checkout <file>` (已具備 `git_checkout`，支援單檔復原與分支切換)
  - **Branch 分支應用**
    - [x] `git branch` (支援 list / checkout / create，已具備 `git_branch`)
    - [x] `git checkout` (已具備 `git_checkout`，支援切換與建立分支)
    - [ ] `git branch -d` / `git branch -D` ⚠️ [高危指令 - 涉及未合併分支丟失風險，暫不開放]
    - [ ] `git branch -m` (分支更名)
  - **Reset 版本回退**
    - [ ] `git reset [--soft|--mixed|--hard] <commit>` ⚠️ [高危指令 - 容易遺失工作區或歷史 Commit，暫不開放]
  - **Rebase & Merge 合併操作**
    - [ ] `git rebase <branch>` ⚠️ [高危指令 - 修改線性歷史且易產生複雜衝突，暫不開放]
    - [ ] `git merge <branch>` ⚠️ [高危指令 - 自動合併衝突易中斷 Pipeline，暫不開放]
  - **查詢與歷史紀錄 (Log / Blame / Reflog)**
    - [x] `git diff` (已具備 `git_diff`)
    - [x] `git log` (已具備 `git_log`，支援 `--max_count`, `--oneline`, `--file_path`)
    - [x] `git blame <file>` (逐行追蹤作者與修改時間，已具備 `git_blame`)
    - [ ] `git reflog` (查詢操作歷史)
    - [ ] `git config --list` / `git --version` (查詢 Git 設定與版本)

### [Phase 6: 架構重構與長期演進規劃 (Roadmap)]
- [ ] **1. Docker 沙盒常駐化 (Long-running Container / Exec 模式) [中高風險]**
  - **背景**：目前每次執行都在臨時容器中 `docker run --rm`，啟動開銷大、跨指令狀態（安裝之套件、快取）無法持久。
  - **規劃**：改為背景常駐 Container (`docker run -d`)，透過 `docker exec` 派發指令；需設計生命週期管理（自動清理、閒置超時停止、健康檢查與孤兒容器回收機制）。
- [ ] **2. 記憶體管理與快照異步化 (Async Snapshots / Worker Thread) [中風險]**
  - **背景**：雖然已實作邊界層延遲聚合快照，但在大規模專案中全量目錄比對與快照寫入仍會佔用主請求線程。
  - **規劃**：評估將 `capture_snapshot` 移至背景執行緒或非同步任務池，避免 API 請求延遲。
- [ ] **3. 專案模組化拆分與依賴解耦 [中風險]**
  - **背景**：`server.py` 與 `executor.py` 承載過多混雜責任（工具註冊、HTTP 服務、路徑檢查、執行期沙盒）。
  - **規劃**：拆分為 `bridge_core`、`handlers/`、`sandbox/` 等獨立模組，並建立完備的單元測試保護網。