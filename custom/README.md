# Hermes 個人客製候選版

上游：NousResearch/hermes-agent 正式版。分支：custom/reliable-delivery。

第一批改造：

- 驗證帳本不將 pytest 的說明、版本、測試收集或 setup plan 當成已執行測試；篩選測試保留 targeted 範圍。
- 記憶與技能送審必須成功保存提案才回報成功；儲存失敗不產生假的 pending id，原資料不變。
- doctor 保留中斷檢查與已完成的部分結果，繼續其他檢查，並以非零退出碼回報未完成。

這些措施不是對任意 shell 指令或模型陳述的完整正確性保證。驗證帳本沿用上游的 opt-in 設定，不擅自修改使用者設定。

## 本機候選版

使用上游 PM 建立獨立測試環境，再執行 `custom/Build-Candidate.ps1`。
腳本要求已提交的乾淨來源、執行相關回歸測試與上游 `scripts/check`、封裝不可變的來源 ZIP，
從 ZIP 解壓後建立獨立 CLI 執行環境並執行 smoke check，最後寫入 SHA-256 manifest。
產物不是 Desktop MSIX，也不是可搬到其他電腦直接安裝的獨立套件。GUI 與真實模型連線不在這次離線驗證範圍。
所有測試使用獨立 profile；不替換已安裝程式、不移轉既有對話、模型、Skills 或憑證。

## 上游更新

目前手動追蹤正式版，未新增自動排程。`custom/Prepare-Upstream.ps1` 查詢最新正式版、驗證來源並建立隔離 worktree。
整合衝突停在候選 worktree，保留原客製分支與現有安裝。從該 worktree 執行 Build-Candidate，傳入取得的 UpstreamTag。
依新版鎖檔重新用 `python -m pm.build_env --source <worktree> --out <new-test-env> --group dev --group test`
建立測試環境，並用 `-TestPython` 指定它，不能沿用舊鎖檔的依賴作為新版相容性證據。
測試、封裝與 smoke 全部通過後才能 fast-forward 客製分支、正常 push（禁止 force push）。安裝另行確認。

GitHub Actions 在此個人 fork 停用，本機編譯不影響其他已登記專案的建置方式。
