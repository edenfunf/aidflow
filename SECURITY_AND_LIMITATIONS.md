# 安全、資料倫理與限制

## 不使用 AI 的範圍

- 平台建立（依災害名稱建議災害類型、組合通報類別與圖層）、同地點多人回報成案、嚴重度分級、審核分流後的案件狀態機、隱私轉換，全部是確定性程式，不經模型。
- 系統不呼叫任何大型語言模型；民眾通報內容與個資不會送往第三方模型服務。

## 身分驗證與存取控制

- 政府管理後台需帳號登入（`AUTH_REQUIRED=true`，正式環境必須開啟）。角色：承辦審核人員、業務主管、系統管理者；權限定義於 `app/domain/permissions.py`，後端每支 API 逐一檢核，前端只決定顯示哪些按鈕。
- 密碼以 Argon2id 雜湊保存；至少 10 字元並含兩種字元類型；管理者建立或重設的密碼可要求使用者首次登入變更（見下）。
- 管理者建立或重設密碼後，可設定使用者首次登入須自行變更（`AUTH_FORCE_PASSWORD_CHANGE`，預設關閉；關閉時使用者可隨時於「帳號設定」自行變更）。
- 連續登入失敗（預設 5 次）鎖定帳號 15 分鐘；帳號不存在時回應相同，避免帳號探測；登入 API 另有每 IP 頻率限制。鎖定機制也可能被用來癱瘓特定帳號（反覆以錯誤密碼嘗試），災時可由系統管理者於帳號管理頁重新啟用，或在主機上執行 `python scripts/unlock_user.py <帳號>` 立即解鎖（`--list` 可列出鎖定中的帳號，解鎖行為寫入稽核紀錄）。
- 登入權杖為 HS256 JWT（`AUTH_SECRET`，預設 12 小時）；變更密碼、停用帳號或變更角色會使舊權杖立即失效。前端權杖存於 sessionStorage，閒置 30 分鐘自動登出。
- `ADMIN_API_KEY`（選用）為系統服務金鑰，帶 `X-API-Key` 的請求具全部權限，僅供排程或整合程式使用。
- `AUTH_REQUIRED=false` 僅供本機開發與自動化測試：未登入的請求視為具全部權限的「開發模式」，後台頂端會顯示警示。
- `DEMO_MODE=true` 會開放示範資料產生器與示範平台清理，正式環境請關閉。

## 個人資料保護

- 民眾免登入、免身分驗證；稱呼、電話、Email 皆為選填。通報表單附個資蒐集告知；Email 僅在勾選「接收案件進度」時用於寄送該案進度，每封信附一鍵取消連結。
- 公開 API（`/v1/public/*`）不輸出姓名、電話、Email、EMIC 案號或門牌：座標粗化至約 110 公尺、地址只保留路段／村里、自由文字中的電話／Email／身分證字號／「我是某某」會被遮蔽。
- 通報者的稱呼、電話、Email 於資料庫以 AES-256-GCM 欄位加密保存（`app/db/crypto.py`，金鑰 `DATA_ENCRYPTION_KEY`）；資料庫備份或被直接查詢時只會看到密文。金鑰遺失即無法解密，請與資料庫備份分開保管。
- 後台只有具 `view_pii` 權限的角色（承辦審核人員、業務主管）在開啟案件或單筆通報時看得到聯絡資料，且每次查閱寫入稽核紀錄（`pii.viewed`）；通報清單與系統管理者一律看不到。
- 上傳照片一律解碼後重新編碼，移除 EXIF／XMP（含手機拍攝位置）並限制尺寸；只接受 JPEG／PNG／WebP，偽裝副檔名的檔案會被拒絕。
- 回報者身分只以加鹽雜湊（`REPORTER_HASH_SALT`）保存於 `reports.reporter_key`，僅用於計算不同回報者。
- 通知紀錄（`notification_logs`）的收件者以遮罩保存。

## 稽核

- 登出會遞增帳號的權杖版本，原本的登入權杖立即失效（不只記錄事件）。
- 服務啟動時會檢查部署設定：`ENVIRONMENT` 非 development 時，`AUTH_SECRET`、`DATA_ENCRYPTION_KEY`、`REPORTER_HASH_SALT` 未設定、`AUTH_REQUIRED=false` 或 `CORS_ORIGINS=*` 都會拒絕啟動，避免以開發設定上線。
- 互動式 API 文件（`/docs`、`/redoc`、`/openapi.json`）僅在開發環境開啟；正式環境關閉，API 回應帶 `X-Frame-Options: DENY` 與 `Content-Security-Policy`。
- 頻率限制與稽核紀錄的來源位址取 `X-Forwarded-For` 的最後一跳，且僅在 `TRUST_FORWARDED_FOR=true`（確實位於反向代理後方）時採用，預設關閉。
- 登入成功／失敗／鎖定、登出、帳號建立與異動、密碼變更、個資查閱、LINE 群組綁定、平台建立與設定、所有案件狀態轉換與審核決定，皆寫入交易型 outbox，介面無法刪改。
- 業務主管與系統管理者可在「稽核紀錄」查詢；平台頁的事件紀錄不含登入與個資查閱等安全事件。

## 濫用防護與傳輸

- 公開端寫入（通報、照片、民眾處理回報）與登入 API 有每 IP 每分鐘上限（`RATE_LIMIT_*`）；目前為單一 API 實例的記憶體計數，多實例部署時請在反向代理加設限制。
- API 回應帶 `X-Content-Type-Options`、`Referrer-Policy`、後台端點 `Cache-Control: no-store`，HTTPS 下加 HSTS。
- 前端除 `/embed/*` 外皆禁止被 iframe 嵌入（`frame-ancestors 'self'`）；嵌入地圖只允許 `EMBED_ALLOWED_ORIGINS` 列出的網站。
- LINE webhook 以 `LINE_CHANNEL_SECRET` 驗證 `X-Line-Signature`，未設定時拒收。

## 官方資料

- 只介接有文件的公開 API；憑證或上游不可用時圖層回報 `disabled` / `unavailable`，不以假資料替代。
- 部分政府網站憑證缺少 Subject Key Identifier，`connectors/base.py` 關閉 OpenSSL strict profile 但保留鏈與主機名驗證。
- 土石流潛勢溪流／崩塌潛勢區為水保署年度圖資，非即時；警戒為即時 JSON。
- 水庫與計畫停電沒有公開座標，地圖位置為鄉鎮示意（`indicative: true`）；台電僅開放計畫性停電。
- 路況消息（TDX）沒有座標，只以文字比對縣市／鄉鎮後列表顯示。

## 已知限制

- **EMIC 介接規格尚未提供**：目前為人工登錄模式（承辦於 EMIC 建案後回填案號、處理狀態與處理單位）。`EMIC_SUBMIT_URL` 的 JSON 上報使用 `app/domain/emic.py` 的暫定欄位對照，取得正式規格後需調整；系統不會偽造 EMIC 回應。
- 民眾協助處理不驗證身分，以承辦確認處理後照片把關；有安全疑慮的災情請審核為「上報 EMIC」。
- Email 與 LINE 通知為盡力而為：失敗寫入通知紀錄，不影響案件狀態；未設定憑證時記錄為模擬。
- 鄉鎮歸屬以最近鄉鎮參考點推定，非權威地理編碼。
- 聚類以平面 bbox 預篩＋haversine 判距；未考慮道路拓撲。
- 案件編號序號以平台內計數產生，重試可處理偶發衝突，但非嚴格連號。
- 本系統是輔助工具，不取代官方災害應變指揮、警報發布與撤離命令。
