# AidFlow 災情通報與處理平台

> ### 線上展示
>
> | | |
> |---|---|
> | **首頁**（選擇災害事件、我要通報） | <https://aidflow.tw> |
> | **民眾通報網站**（示範情境：南投縣豪雨） | <https://aidflow.tw/p/nantou-heavy-rain-demo> |
> | **嵌入地圖**（縣府網站 iframe 用） | <https://aidflow.tw/embed/nantou-heavy-rain-demo> |
> | **政府管理後台**（需登入） | <https://aidflow.tw/console> |
> | **API / Swagger** | <https://api.aidflow.tw/docs> |
>
> 展示站以 `DEMO_MODE` 執行；政府管理後台需帳號登入（見 [SECURITY_AND_LIMITATIONS.md](./SECURITY_AND_LIMITATIONS.md)）。

依 2026-09-03 南投縣政府需求會議調整：民眾免登入通報，同地點多人回報自動成案，**承辦人員審核後分流**為「上報 EMIC」或「開放民眾協助處理」，處理進度公開於災情地圖。

```text
民眾通報（可選填 Email 接收進度）
  → 同地點通報聚合（距離／時間窗／相近類別，同一人重複不計）
  → LINE BOT 推播縣府群組
  → 待審核（依嚴重程度排序；也可人工成案）
       ├─ 上報 EMIC   → 回填 EMIC 案號／處理狀態／處理單位 → 處理中 → 結案
       ├─ 民間可處理 → 民眾「我來協助處理」上傳處理後照片 → 承辦確認 → 結案（退回可重開）
       └─ 不成案
  → 結案的災情自公開地圖撤除
```

聚合、成案門檻、嚴重度分級與案件狀態機都是確定性程式，不經 AI；每一步寫入案件事件（公開時間軸）與 outbox（稽核紀錄）。

## 頁面一覽

| 路徑 | 用途 |
|---|---|
| `/` | 首頁：開放通報的災害事件、我要通報、政府人員登入 |
| `/p/{slug}` | 民眾端災情地圖：處理進度、可選資料圖層、醒目的「我要通報」 |
| `/p/{slug}/report` | 通報表單：類別、GPS／地圖選點、照片、描述、選填聯絡資料與進度通知 |
| `/p/{slug}/cases`、`/cases/{id}` | 全部災情與處理進度；民間可處理案件有「我來協助處理」 |
| `/embed/{slug}` | 精簡嵌入地圖，僅允許 `EMBED_ALLOWED_ORIGINS` 內的網站以 iframe 嵌入 |
| `/p/{slug}/wall` | 應變中心戰情牆（自動輪播） |
| `/unsubscribe` | 取消案件進度通知（通知信內連結） |
| `/login` | 政府管理後台登入 |
| `/console` | 災害平台清單（待審核、EMIC 處理中、民眾協助） |
| `/console/platforms/{id}` | 平台後台：嚴重程度分級卡、LINE 群組通知狀態、地圖＋審核／案件佇列、未成案地點、通知紀錄、成案規則 |
| `/console/platforms/{id}/cases/{caseId}` | 案件工作台：審核點、EMIC 登錄、民間處理確認、處理紀錄 |
| `/console/new` | 建立災害平台：輸入災害名稱、確認災害類型與縣市鄉鎮（系統管理者） |
| `/console/users`、`/console/audit`、`/console/account` | 帳號管理、稽核紀錄、變更密碼 |

## 角色與權限

| 功能 | 民眾 | 承辦審核人員 | 業務主管 | 系統管理者 |
|---|:-:|:-:|:-:|:-:|
| 通報、看地圖、訂閱進度、協助處理 | ● | ● | ● | ● |
| 後台總覽與案件（唯讀） | — | ● | ● | ● |
| 審核分流、EMIC 登錄、處理紀錄、民間處理確認、人工成案 | — | ● | — | — |
| 檢視通報者聯絡資料（留存查閱紀錄） | — | ● | ● | — |
| 建立平台、成案規則、LINE 群組綁定、帳號管理 | — | — | — | ● |
| 稽核紀錄查詢 | — | — | ● | ● |

權限定義在 `apps/api/app/domain/permissions.py`，每支後台 API 逐一檢核。

## 快速啟動

需求：Docker 與 Docker Compose。

```bash
cp .env.example .env        # 至少填 POSTGRES_PASSWORD、AUTH_SECRET、INITIAL_ADMIN_PASSWORD
docker compose up --build
ADMIN_USERNAME=admin ADMIN_PASSWORD=<INITIAL_ADMIN_PASSWORD> bash client/seed_demo.sh
```

- 首頁：<http://localhost:3000>
- 政府管理後台：<http://localhost:3000/console>（首次以 `admin` 登入後須變更密碼，再到「帳號管理」建立承辦與主管帳號）
- API / Swagger：<http://localhost:8000/docs>

API 啟動時自動執行 Alembic migration；資料庫沒有任何帳號時，以 `INITIAL_ADMIN_*` 建立第一位系統管理者。

### Demo 路徑

1. 系統管理者到 `/console/new` 輸入「115 年 0903 豪雨」，確認災害類型（依名稱自動建議）與鄉鎮，建立平台。
2. 平台後台點「設定 LINE 群組通知」，依三步驟把 LINE 機器人加入群組並輸入「綁定 代碼」。
3. 民眾在 `/p/{slug}/report` 送出「道路坍方」並勾選接收進度；另一台裝置在附近送出同類通報 → 自動成案，LINE 群組收到「待審核」。
4. 承辦人員在「待審核」（依嚴重度排序）開啟案件 →「上報 EMIC」→ 在 EMIC 建案後回填案號、處理狀態與處理單位 →「處理完成・結案」。
5. 另一件倒木案 →「民間可處理」→ 民眾在案件頁「我來協助處理」上傳處理後照片 → 承辦「確認通過・結案」，災情自地圖撤除。
6. 訂閱進度的民眾在每次狀態變更時收到 Email（未設定 SMTP 時記錄為模擬）。

### 通知與介接

| 管道 | 用途 | 設定 | 未設定時 |
|---|---|---|---|
| LINE Messaging API | 新通報／待審核／民眾回報已處理 → 縣府 LINE 群組 | `LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET`（webhook `/v1/line/webhook`） | 記錄為「模擬」 |
| Email（SMTP） | 案件進度通知訂閱的民眾，附取消連結 | `SMTP_*` | 記錄為「模擬」 |
| EMIC | 上報案件 | `EMIC_SUBMIT_URL`、`EMIC_API_TOKEN`；欄位對照見 `app/domain/emic.py`（暫定） | 人工登錄模式：承辦回填 EMIC 案號與狀態 |

所有通知寫入 `notification_logs`（收件者遮罩），後台「LINE 通知」分頁可查。

### 官方資料介接

| 來源 | 圖層 | 憑證 |
| --- | --- | --- |
| 經濟部水利署 水利資料開放平台 | 河川水情、水庫水情 | 無需 |
| 內政部消防署 避難收容處所點位檔 | 避難收容 | 無需 |
| 南投縣政府資料開放平台 CKAN | 消防單位 | 無需 |
| 中央氣象署 開放資料 | 雨量、官方警戒、雷達回波 | `CWA_API_KEY` |
| 農村發展及水土保持署 | 土石流潛勢溪流、大規模崩塌潛勢區 | 無需 |
| 交通部 TDX | 路況 CCTV、路況消息 | `TDX_CLIENT_ID/SECRET` |
| 內政部戶政司、台電 | 人口分布、計畫停電 | 無需 |
| NCDR 民生示警（CAP） | 官方警戒 | `NCDR_CAP_FEED_URL` |

來源經 `Connector → Normalizer → GeoFeature` 統一格式；上游失敗時圖層回報 `unavailable`，不以假資料替代。民眾端可在「資料圖層」自行開關。

## API 概覽

| Method | Path | 說明 |
| --- | --- | --- |
| POST | `/v1/auth/login`、`/logout`、`/password`；GET `/v1/auth/me` | 登入、登出、變更密碼、目前使用者 |
| GET/POST/PATCH | `/v1/users`、`/v1/users/{id}` | 帳號管理（系統管理者） |
| GET | `/v1/admin/audit` | 稽核紀錄（登入、帳號、個資查閱、設定） |
| GET/POST | `/v1/platforms/options`、`/v1/platforms/preview`、`/v1/platforms` | 災害類型／縣市選項、依名稱預覽、建立平台 |
| GET/POST/PATCH | `/v1/platforms/{id}`、`/status`、`/overview`、`/map`、`/reports`、`/clusters`、`/layers`、`/audit`、`/notifications` | 平台後台 |
| GET/PUT/DELETE/POST | `/v1/platforms/{id}/line`、`/line/code`、`/line/test` | LINE 群組綁定 |
| GET | `/v1/platforms/{id}/cases?phase=pending\|active\|community\|done`、`/v1/cases/{id}` | 審核／案件佇列、案件詳情 |
| POST | `/v1/cases/{id}/review` | 審核點：`emic`／`community`／`dismiss` |
| POST | `/v1/cases/{id}/emic` | 登錄 EMIC 案號、處理狀態、處理單位，可改處理中／結案 |
| POST | `/v1/cases/{id}/community/confirm` | 確認民眾處理完成（通過結案／退回） |
| POST | `/v1/cases/{id}/transition`、`/updates`、`/photos` | 狀態轉換、處理紀錄、照片 |
| POST | `/v1/platforms/{id}/clusters/{cid}/promote`、`/v1/reports/{id}/reject` | 人工成案、排除通報 |
| GET | `/v1/public/platforms/{slug}`、`/situation`、`/map`、`/cases`、`/cases/{id}`、`/reports`、`/layers/{layer}` | 公開端（去識別化；結案案件不在地圖上） |
| POST | `/v1/public/platforms/{slug}/reports`、`/v1/public/reports/{id}/photos` | 民眾通報與照片（每 IP 頻率限制） |
| POST | `/v1/public/platforms/{slug}/cases/{id}/community-report` | 民眾回報已協助處理（處理後照片） |
| POST | `/v1/public/unsubscribe` | 取消進度通知 |
| POST | `/v1/line/webhook` | LINE webhook（簽章驗證，群組綁定） |

完整合約見 Swagger（`/docs`）或 [openapi/](./openapi/)；交換格式見 [schemas/](./schemas/)。

## 目錄結構

```text
apps/
├── api/                            FastAPI
│   ├── app/domain/                 純規則：災情類別、災害分類、案件狀態機、角色權限、EMIC 欄位對照
│   ├── app/core/                   設定、身分驗證與權限檢核
│   ├── app/modules/                模組註冊表、情境組合
│   ├── app/services/               composer、clustering、case（審核／EMIC／民間處理）、auth、notification、
│   │                               line 綁定、privacy、official data、media（去除 EXIF）、demo seed
│   ├── app/connectors/             官方資料 + line / mailer / emic
│   ├── app/routers/                public / auth / platforms / cases / modules / demo / line
│   ├── alembic/versions/           …0014 審核分流、帳號、通知紀錄、LINE 群組；移除派遣
│   └── tests/                      規則、聚類、隱私、權限、審核流程、LINE、demo 一致性
└── web/                            Next.js + Tailwind + MapLibre GL
    ├── app/p/[slug]/               民眾通報網站
    ├── app/embed/[slug]/           嵌入地圖
    ├── app/console/                政府管理後台
    └── components/                 TerrainMap、portal/Hud、console/LinePanel、CaseTimeline…
```

## 測試

```bash
docker compose exec api pytest -q      # 後端
python scripts/validate_schemas.py     # JSON Schema 與範例
cd apps/web && npx tsc --noEmit && npm run build
```

## 資料倫理與限制

見 [SECURITY_AND_LIMITATIONS.md](./SECURITY_AND_LIMITATIONS.md)。本系統為政府災害應變的輔助工具，公開資訊以各主管機關正式公告為準。

## 授權

MIT，見 [LICENSE](./LICENSE)。
