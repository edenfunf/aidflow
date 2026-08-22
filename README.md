# AidFlow

> ### 線上展示
>
> | | |
> |---|---|
> | **系統控制台**（輸入災害背景 → 生成平台） | <https://aidflow.tw> |
> | **民眾通報網站**（示範情境：南投縣豪雨） | <https://aidflow.tw/p/nantou-heavy-rain-demo> |
> | **戰情牆**（全螢幕環繞） | <https://aidflow.tw/p/nantou-heavy-rain-demo/wall> |
> | **API / Swagger** | <https://api.aidflow.tw/docs> |
>
> 站上「政府管理後台」的連結在系統控制台的平台卡片上。展示站以 `DEMO_MODE` 執行、
> 未設 `ADMIN_API_KEY`，任何人都可以生成平台與送出通報——這是為了讓評審直接試用，
> 不是正式部署的權限設定（見 [SECURITY_AND_LIMITATIONS.md](./SECURITY_AND_LIMITATIONS.md)）。
> 生成出來的平台不累積：只保留最新一個，示範平台永遠保留。

**災害情境驅動的災情平台生成器** — 輸入一段災害背景描述，系統理解情境、從模組註冊表挑選功能模組與資料圖層，經人工確認後生成一套「公開災情通報與視覺化網站」與「政府災情管理後台」。

```text
LLM（理解／建議，可退回關鍵字規則）
  ↓
Human Approval（人工確認模組、圖層、通報類別、成案規則）
  ↓
Deterministic Composer（依模組註冊表生成平台）
  ↓
Public Disaster Portal  +  Government Operations Console
```

平台建立後的核心治理流程完全由確定性程式執行，不經模型：

```text
Report → Normalize → Geo Cluster → Duplicate Check
  → unique_reporters ≥ threshold（預設同地點 2 位不同回報者）
  → Create Incident Case → awaiting_dispatch → assigned → en_route → on_site
  → processing → resolved → closed
```

每一步都寫入案件事件（公開時間軸）與事件 outbox（稽核軌跡）。


## 頁面一覽

| 路徑 | 用途 |
|---|---|
| `/` | **系統控制台**：輸入災害背景 → 生成平台；已生成平台以「民眾通報網站／政府管理後台」兩張門卡呈現 |
| `/p/{slug}` | 公開災情入口：3D 地形態勢、標竿案件、出勤路線與車輛、時間回放、環繞鏡頭 |
| `/p/{slug}/cases` | 案件列表＋側邊地圖（點列表飛到該案） |
| `/p/{slug}/cases/{id}` | 案件詳情：該案地形視角、處理進度、時間軸（事件圖示）、處理前後比對滑桿 |
| `/p/{slug}/report` | 通報表單：類別圖示、同款向量底圖選點＋GPS 精度圈、成案進度環 |
| `/p/{slug}/wall` | 戰情牆／展場 kiosk：全螢幕自動環繞，側欄輪播最新案件、出勤車輛、鄉鎮分布、趨勢 |
| `/console` | 指揮中心：平台總覽、即時事件流、案件佇列、派遣；右上可切換深色戰情配色；生成平台時預設同時帶入示範資料（`POST /v1/platforms/{id}/demo`，`replace=true` 先清空），落地即有完整案件 |

## 兩套介面

| | Public Disaster Portal `/p/{slug}` | Government Operations Console `/console/platforms/{id}` |
| --- | --- | --- |
| 使用者 | 民眾、村里長、防災士、志工、媒體 | 縣府應變中心、處理單位 |
| 地圖 | **3D 地形態勢圖**（MapLibre，免金鑰底圖與高程）：案件標竿（高度＝回報人數）、狀態環、未成案聚類、去識別化通報、熱區、官方圖層（雷達／雨量／警戒／土石流／避難所）、24 小時回放 | **同一張 3D 地形圖**，另加作業圖層：出勤車輛與路徑、水庫水情、河川水位、CCTV |
| 資料 | 即時態勢 KPI、最新災情、處理進度、24 小時趨勢、官方警戒摘要 | 案件佇列（嚴重度／時間／地區／人數／狀態／類別）、未達門檻聚類、內部通報（含 PII）、圖層健康、成案規則、稽核軌跡 |
| 動作 | 提交通報（行動優先表單：類別→定位→照片→描述→身分） | 縣府確認派工、狀態機轉換、公開進度、前後對照照片、排除不實通報 |

兩端共用同一份 Platform / Report / ReportCluster / IncidentCase 資料；公開端一律經隱私轉換（座標粗化、地址遮罩、個資與電話去識別化）。

**預設圖層依角色分工**：通報端回答「哪裡危險、我要去哪通報」，預設開官方警戒、雷達回波、土石流潛勢；政府出勤（車輛與路徑）預設關閉，但保留切換以示公開透明。指揮中心回答「現在誰在處理什麼」，預設開出勤與天氣。

## 快速啟動

需求：Docker 與 Docker Compose。

```bash
cp .env.example .env        # 至少填 POSTGRES_PASSWORD
docker compose up --build
bash client/seed_demo.sh    # 載入「南投縣豪雨」示範情境（走真實 pipeline）
```

- 公開入口：<http://localhost:3000>
- 後台：<http://localhost:3000/console>
- API / Swagger：<http://localhost:8000/docs>

API 啟動時自動執行 Alembic migration（fresh install 與從既有資料庫升級皆可）。

### 完整 Demo 路徑

1. `/console/new` 輸入：「南投縣仁愛鄉因豪雨造成道路坍方、土石流與積淹水，希望建立全民災情通報與即時處理平台。」
2. 系統分析地區／災害／災情／回報者，建議通報類別、模組、圖層、成案規則與處理流程。
3. 人工調整後「確認並建立平台」→ 取得公開網站與指揮中心連結。
4. 開啟 `/p/{slug}`：地圖、官方資料、統計、最新案件。
5. `/p/{slug}/report` 送出第一筆「道路坍方」通報（表單會帶入裝置識別）。
6. 用另一個瀏覽器／無痕視窗在附近送出同類通報 → 系統判定同一災點、Unique Reporters = 2 → 自動成案。
7. 指揮中心立即出現「待派工」→ 指定處理單位（派工）。
8. 公開端顯示「已派員」；後台依序按「人員抵達 → 開始處理 → 處理完成」。
9. 公開案件頁時間軸即時呈現完整處理過程。

### 啟用 AI 情境解析（選用）

在 `.env` 填 `OPENAI_API_KEY`。AI 只負責理解描述並從封閉選項中挑選（縣市／鄉鎮／災害／災情類別／回報者），任何失敗自動退回關鍵字規則；平台生成本身不依賴模型。

### 官方資料介接

| 來源 | 圖層 | 憑證 | 狀態 |
| --- | --- | --- | --- |
| 經濟部水利署 水利資料開放平台（河川水位測站站況＋即時水位） | 河川水情 | 無需 | 直接介接 |
| 內政部消防署 避難收容處所點位檔（data.gov.tw 73242） | 避難收容 | 無需 | 直接介接（依縣市篩選） |
| 南投縣政府資料開放平台 CKAN（消防局各單位地圖） | 消防單位 | 無需 | 直接介接 |
| 中央氣象署 開放資料（雨量站 O-A0002-001、天氣特報 W-C0033-001、地震報告 E-A0015-001） | 雨量、官方警戒 | `CWA_API_KEY` | 未設定時圖層顯示「尚未設定金鑰」 |
| NCDR 民生示警公開資料平台（CAP） | 官方警戒 | `NCDR_CAP_FEED_URL`（需會員授權） | 未設定時不可用 |

所有來源經 `Connector → Normalizer → GeoFeature` 統一格式，前端不理解政府 API schema；上游失敗時圖層回報 `unavailable`，網站照常運作，不會以假資料替代。

### 出勤派遣與即時車輛

- **權責規則**（`app/domain/responders.py`）：人員受困／火災／瓦斯／醫療 → 消防；道路坍方／中斷／橋梁 → 公路局工務段／公所；土石流 → 水保署；積淹水／堤防 → 水利署河川分署；停電 → 台電。
- **單位登錄**：消防單位取自南投縣政府開放資料（測量座標）；其他機關為設定檔，位置以鄉鎮示意並標示。
- **一鍵通報並派遣**（`POST /v1/cases/{id}/dispatch`）：建立派工、以 OSRM 沿真實道路算出路徑與 ETA、把案件資訊送給單位（LINE 推播／`DISPATCH_WEBHOOK_URL`／模擬紀錄）、寫入公開時間軸與稽核。
- **即時車輛**：台灣沒有公開的消防／警察車輛即時位置 API。系統提供 `POST /v1/avl/positions` 讓縣府車隊系統推送 GPS（優先顯示、標示「即時」）；沒有 AVL 時，依派遣時間沿路徑推算位置並標示「模擬」，案件完成後車輛返隊。

### 存取控制

設定 `ADMIN_API_KEY` 後，`/v1/public/*` 與 `/v1/health` 以外的端點都需 `X-API-Key`。後台右上角可把 key 存在瀏覽器。

## API 概覽

| Method | Path | 說明 |
| --- | --- | --- |
| POST | `/v1/agent/plan` | 理解災害描述 → 情境分析 + 建議模組／圖層／類別／成案規則（不寫入） |
| POST | `/v1/agent/execute` | 人工確認的草案 → 確定性生成平台 |
| GET | `/v1/modules`、`/v1/modules/domains`、`/v1/connectors` | 模組註冊表與介接狀態 |
| GET/POST/PATCH | `/v1/platforms`、`/v1/platforms/{id}`、`/status`、`/overview`、`/map`、`/reports`、`/clusters`、`/layers`、`/audit` | 平台管理與指揮中心 |
| GET | `/v1/platforms/{id}/cases`、`/v1/cases/{id}` | 案件佇列／案件詳情（含所有回報） |
| POST | `/v1/cases/{id}/assign`、`/transition`、`/updates`、`/photos` | 派工、狀態機、公開進度、單位照片 |
| GET/POST | `/v1/cases/{id}/responders`、`/v1/cases/{id}/dispatch` | 建議出勤單位（規則→距離→道路 ETA）、通報並派遣 |
| GET | `/v1/platforms/{id}/units`、`/vehicles`、`/routes`；`/v1/public/platforms/{slug}/vehicles`、`/routes` | 單位登錄、出勤車輛、出勤路徑 |
| POST | `/v1/avl/positions` | 車隊 GPS 推送（AVL） |
| POST | `/v1/platforms/{id}/clusters/{cid}/promote`、`/v1/reports/{id}/reject` | 人工成案、排除通報 |
| GET | `/v1/public/platforms/{slug}`、`/situation`、`/map`、`/cases`、`/cases/{id}`、`/reports`、`/layers/{layer}` | 公開端（去識別化） |
| POST | `/v1/public/platforms/{slug}/reports`、`/v1/public/reports/{id}/photos` | 民眾通報與照片 |
| POST | `/v1/demo/nantou` | 示範情境（`DEMO_MODE`） |

完整合約見 Swagger（`/docs`）或 [openapi/](./openapi/)；交換格式見 [schemas/](./schemas/)。

## 目錄結構

```text
apps/
├── api/                            FastAPI
│   ├── app/domain/                 純規則：災情類別、災害分類、案件狀態機
│   ├── app/modules/                模組註冊表（9 大領域、功能／圖層／處理引擎／介接）、情境組合
│   ├── app/services/               planner、composer、clustering、case、privacy、official data、media、demo seed
│   ├── app/connectors/             nantou_open_data / moi_shelters / moi_population / wra / cwa /
│   │                               ncdr / ardswc / tdx / taipower / osrm / line
│   ├── app/routers/                public / agent / platforms / cases / modules / demo
│   ├── alembic/versions/           0010 AidFlow core、0011 retire ResQLink、0012 case number scope
│   └── tests/                      單元（規則、聚類、隱私、normalizer）+ 整合（planner→case→timeline）
└── web/                            Next.js + Tailwind + MapLibre GL（3D 地形，兩端共用）
    ├── app/p/[slug]/               Public Portal（態勢、案件、案件詳情、通報表單）
    ├── app/console/                Console（平台、規劃器、指揮中心、案件工作台、註冊表、介接）
    └── components/                 TerrainMap（3D）、portal/Hud、IncidentMap、TrendChart、CaseTimeline、PhotoStrip…
```

## 測試

```bash
docker compose exec api pytest -q      # 後端（含 2-person trigger、狀態機、隱私、connector fallback、demo 一致性）
python scripts/validate_schemas.py     # JSON Schema 與範例
cd apps/web && npx tsc --noEmit && npm run build
```

## 資料倫理與限制

見 [SECURITY_AND_LIMITATIONS.md](./SECURITY_AND_LIMITATIONS.md)。本系統為政府災害應變的輔助工具，公開資訊以各主管機關正式公告為準。

## 授權

MIT，見 [LICENSE](./LICENSE)。

## 官方資料來源（第二波）

| 圖層 | 來源 | 取得方式 | 視覺化 |
|---|---|---|---|
| 雷達回波 `radar` | 中央氣象署 檔案 API O-A0058-005（透明圖層） | `CWA_API_KEY` | 貼在 3D 地形上的 raster，保留最近 12 幀自動回放 |
| 土石流潛勢溪流 `debris_flow` | 水保署 年度圖資 SHP（data.gov.tw 176524/176526）＋警戒 JSON | 公開 | 潛勢溪流線（風險色）、影響範圍面；紅／黃警戒加粗發光 |
| 大規模崩塌潛勢區 `landslide_zone` | 水保署 年度圖資 SHP（176527）＋警戒 JSON | 公開 | 潛勢區面，警戒變色 |
| 路況 CCTV `road_traffic` | 交通部 TDX 路況 v2（CCTV、路況消息） | `TDX_CLIENT_ID/SECRET` | 監視器點位＋彈窗即時截圖；封閉／坍方消息在指揮中心與案件頁 |
| 水庫水情 `reservoir` | 水利署 水庫基本資料＋水庫水情 | 公開 | 蓄水率標籤、洩洪狀態色（位置為鄉鎮示意） |
| 人口分布 `population` | 內政部戶政司 ODRP013 各村里人口 | 公開 | 鄉鎮比例圓＋人口標籤；指揮中心「每萬人案件」 |
| 計畫停電 `power_outage` | 台電 計畫性工作停電（data.gov.tw 26144） | 公開 | 鄉鎮件數點；台電未開放事故停電資料 |

所有圖資皆以 API 回應或官方檔案即時解析，抓不到就顯示「暫時無法取得」。
