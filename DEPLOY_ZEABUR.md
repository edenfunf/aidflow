# Zeabur 部署手冊

AidFlow 已經部署在 Zeabur，同一個專案裡三個服務：**PostgreSQL ＋ FastAPI 後端 ＋ Next.js 前端**。
兩個 Dockerfile（`apps/api/Dockerfile`、`apps/web/Dockerfile`）就是部署設定，不需要額外的 YAML。

```
使用者 ──► aidflow-web（Next.js） https://aidflow.tw
               │  同網域推導出 api.<host>，或用 NEXT_PUBLIC_API_BASE_URL 覆寫
               ▼
           aidflow-api（FastAPI，開機自動跑 alembic upgrade head） https://api.aidflow.tw
               │  DATABASE_URL = ${POSTGRES_CONNECTION_STRING}
               ▼
           PostgreSQL（Zeabur 服務）
```

## 現況（已完成）

| 項目 | 值 |
| --- | --- |
| Project | `aidflow` — `6a89f78d9c1441c21a54db64` |
| Environment | production — `6a89f78dcac6c1b35ed69fe8` |
| Region | `server-6a4694d7550ec10c8eeaf7b9`（自有 Server，Tencent Tokyo 2C/4GB） |
| PostgreSQL | `6a89f8344eb432b6e4cf6493`（Template `B20CX0`） |
| aidflow-api | `6a89f914421445b84c30d18d` → `api.aidflow.tw` |
| aidflow-web | `6a89fbb8421445b84c30d257` → `aidflow.tw`、`www.aidflow.tw`（302 導向主網域） |

網址：

- 民眾通報網站 <https://aidflow.tw/p/{slug}>
- 嵌入地圖 <https://aidflow.tw/embed/{slug}>
- 政府管理後台（需登入） <https://aidflow.tw/console>
- 戰情牆 <https://aidflow.tw/p/{slug}/wall>
- API 健康檢查 <https://api.aidflow.tw/v1/health>

> **注意：Shared cluster 已被 Zeabur 停用**。用 API 建服務時 region 必須填自有 Server 的
> `server-XXXXXXXX` 代碼，否則會被拒絕。Marketplace（`createPrebuiltService`）同樣已停用，
> 資料庫要改用 `deployTemplate(code: "B20CX0")`。

## 重新部署（不透過 GitHub）

專案沒有接 GitHub remote，直接用 CLI 從本機上傳：

```bash
npx zeabur@latest auth login          # 或 export ZEABUR_TOKEN=...
cd apps/api && npx zeabur@latest deploy --service aidflow-api
cd ../web && npx zeabur@latest deploy --service aidflow-web
```

CLI 會問 project / environment，選 `aidflow` / `production`。
後端每次啟動都會自己跑 `alembic upgrade head`，不用手動 migrate。

## 環境變數

後端（`aidflow-api`）：

| 變數 | 值 | 說明 |
| --- | --- | --- |
| `DATABASE_URL` | `${POSTGRES_CONNECTION_STRING}` | Zeabur 服務間變數，會自動展開 |
| `AUTH_REQUIRED` | `true` | 後台端點需登入 |
| `AUTH_SECRET` | （祕密，32 字元以上隨機字串） | 登入權杖簽章；未設定時服務拒絕啟動 |
| `DATA_ENCRYPTION_KEY` | （祕密，`openssl rand -hex 32`） | 通報者稱呼／電話／Email 加密保存；請備份，不可更換 |
| `INITIAL_ADMIN_PASSWORD` | （祕密） | 資料庫沒有帳號時建立 `admin`；登入後請自行變更密碼 |
| `API_PUBLIC_BASE_URL` | `https://api.aidflow.tw` | 照片等公開檔案的完整網址 |
| `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_CHANNEL_SECRET` | （祕密） | 縣府 LINE 群組通知；webhook 設為 `https://api.aidflow.tw/v1/line/webhook` |
| `SMTP_HOST` 等 `SMTP_*` | （選用） | 民眾進度通知信；未設定時記錄為模擬 |
| `EMIC_SUBMIT_URL` / `EMIC_API_TOKEN` | 未設定 | EMIC 規格提供前維持人工登錄 |
| `DEMO_MODE` | `false` | `true` 才開放示範資料帶入與平台清理（示範用；正式環境維持 `false`） |
| `DEMO_KEEP_GENERATED` | `1`（預設） | 生成的平台只留最新一個，內建南投示範平台永遠保留 |
| `CORS_ORIGINS` | `https://aidflow.tw` | 允許呼叫 API 的前端網域，逗號分隔；不可用 `*` |
| `TRUST_FORWARDED_FOR` | `true` | Zeabur 在反向代理後方，頻率限制才看得到真實來源位址 |
| `WEB_PUBLIC_BASE_URL` | `https://aidflow.tw` | 產生對外連結用 |
| `MEDIA_ROOT` | `/app/media` | 上傳檔案位置 |
| `REPORTER_HASH_SALT` | （祕密） | 通報者去識別化雜湊鹽；未設定時服務拒絕啟動 |
| `CWA_API_KEY` | （祕密） | 中央氣象署：雷達、雨量、警特報 |
| `TDX_CLIENT_ID` / `TDX_CLIENT_SECRET` | （祕密） | TDX：CCTV、路況 |
| `NCDR_CAP_FEED_URL` | 未設定 | 未設定時 `official_alert` 圖層會標註來源缺漏 |

沒有金鑰的官方資料（水利署、水保署、內政部、台電、南投 CKAN）不需設定就會運作。

前端（`aidflow-web`）：`EMBED_ALLOWED_ORIGINS`（建置時讀取）列出可用 iframe 嵌入 `/embed/{slug}` 的縣府網站，例如 `https://www.nantou.gov.tw`；其餘不需要變數。`apps/web/lib/api.ts` 在 `NEXT_PUBLIC_API_BASE_URL`
為空時，會從目前網域推導出 `api.<host>`；`apps/web/Dockerfile` 的
`ARG NEXT_PUBLIC_API_BASE_URL=""` 就是刻意留空讓這個推導生效。
若前後端不是同一個母網域，才需要在 build 時傳入完整 API 網址。

## 綁定網域

Zeabur 主控台 → 服務 → **Domains** → Add Domain。`aidflow.tw` 是在 Zeabur 買的網域，
DNS 由 Zeabur 代管，加完即生效，憑證自動簽發。

## 部署後檢查

```bash
curl -s https://api.aidflow.tw/v1/health          # auth_required 應為 true
curl -s https://api.aidflow.tw/v1/public/platforms
# 後台端點需先登入取得權杖（系統管理者）
TOKEN=$(curl -s -X POST https://api.aidflow.tw/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<密碼>"}' | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
# 需要時手動帶入示範資料
curl -s -X POST -H "Authorization: Bearer $TOKEN" https://api.aidflow.tw/v1/platforms/{platform_id}/demo
```

## 祕密管理

金鑰只放在 Zeabur 的 Variables 與本機 `.env`（已被 `.gitignore` 忽略），
不會進入 repo。輪替 Zeabur API token：Zeabur → Settings → Developer → API Tokens。
