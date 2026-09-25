### LLM 已知BUG 列表
- [x] gemini側邊欄開啟的狀況下無法按下發送按鈕(此bug原本是會按下側邊欄對話紀錄的三個點按鈕)
- [x] poll_job_status 在正確回傳狀態(status=success)的情況下batch array卻顯示status=false，導致後續動作無法被中斷