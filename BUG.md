### LLM 已知BUG 列表
- [x] gemini側邊欄開啟的狀況下無法按下發送按鈕(此bug原本是會按下側邊欄對話紀錄的三個點按鈕)
- [x] poll_job_status 在正確回傳狀態(status=success)的情況下batch array卻顯示status=false，導致後續動作無法被中斷
- [x] 前端至後端 Bridge 工具傳輸層 XML/HTML 字元吞食導致語法毀損 (v4.15.3 移除破壞性角括號正則)
- [x] execute_async 缺乏 timeout 保護與外部 kill_job 控制機制 (已實作非阻塞輪詢監控、超時強制清理、手動中斷指令與 elapsed time 即時追蹤)
