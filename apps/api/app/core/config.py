from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # No default on purpose: the connection string carries credentials, so it
    # must come from the environment (docker-compose / the managed host).
    DATABASE_URL: str

    # Optional API key gate: when set, government/console endpoints require the
    # X-API-Key header to match. Empty (default) keeps the open demo mode.
    ADMIN_API_KEY: str = ""

    # Comma-separated allowed CORS origins, or "*" for any origin
    # (credentials are disabled automatically in that case).
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001"
    )

    APP_NAME: str = "AidFlow API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    # Demo mode: enables the demo scenario seeder (/v1/demo/*). Turn off in
    # production so nobody can inject synthetic reports into a live platform.
    DEMO_MODE: bool = True
    # 示範情境下，生成出來的平台不累積：只保留最新 N 個（0 = 全部保留）。
    # 內建的南投示範平台永遠保留。
    DEMO_KEEP_GENERATED: int = 1

    # ── AI layer (optional). Used only for scenario understanding in the agent
    # planner; platform generation itself is deterministic.
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # ── Deterministic clustering defaults (per-platform policy overrides these).
    CLUSTER_REQUIRED_UNIQUE_REPORTERS: int = 2
    CLUSTER_RADIUS_METERS: int = 100
    CLUSTER_TIME_WINDOW_MINUTES: int = 60

    # ── Media storage for citizen photos (local filesystem abstraction).
    MEDIA_ROOT: str = "./media"
    MEDIA_MAX_BYTES: int = 8 * 1024 * 1024

    # Pepper for hashing reporter identities (device key / contact) into an
    # opaque reporter_key. Change per deployment.
    REPORTER_HASH_SALT: str = "aidflow-dev-salt"

    # ── Official open-data connectors ───────────────────────────────────────
    # 中央氣象署 CWA open data (雨量站 O-A0002-001 / 天氣特報 W-C0033-001 /
    # 地震報告 E-A0015-001). Requires a free authorization key.
    CWA_API_KEY: str = ""
    CWA_API_BASE: str = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"

    # 經濟部水利署 水利資料開放平台 (public, no key): 河川水位測站站況 +
    # 即時水位資料 (data.gov.tw 22227 / 25768).
    WRA_API_BASE: str = "https://opendata.wra.gov.tw/api/v2"
    WRA_STATION_DATASET: str = "c4acc691-7416-40ca-9464-292c0c00da92"
    WRA_WATER_LEVEL_DATASET: str = "73c4c3de-4045-4765-abeb-89f9f9cd5ff0"

    # 南投縣政府資料開放平台 (CKAN, public): DataStore resources.
    NANTOU_CKAN_BASE: str = "https://data.nantou.gov.tw/api/3/action"
    # 南投縣消防局各單位地圖 (消防單位點位，含經緯度)
    NANTOU_FIRE_STATION_RESOURCE: str = "46bb0e1d-78d1-4c6c-8a8f-4fc4e29fca36"

    # 內政部消防署 避難收容處所點位檔 (data.gov.tw 73242, no-auth CSV).
    MOI_SHELTER_CSV_URL: str = (
        "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
        "ED6CF735-6C03-4573-A882-72C1BEC799CB/resource/"
        "54550E2F-4567-4C8F-BD2E-E54E9D0386B8/download"
    )

    # 中央氣象署 檔案 API（雷達整合回波透明圖層 O-A0058-005；同一把 CWA_API_KEY）
    CWA_FILE_API_BASE: str = "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi"
    CWA_RADAR_DATASET: str = "O-A0058-005"
    # 文件記載之圖幅範圍 W,S,E,N（回應若帶座標則以回應為準）
    CWA_RADAR_BOUNDS: str = "115.0,17.75,126.5,29.25"
    CWA_RADAR_FRAMES: int = 8
    # 原圖為 3600×3600、涵蓋 115–126.5E：裁到台灣附近並縮圖後才送到瀏覽器
    # （否則每換一幀就要解碼並上傳一張約 50 MB 的貼圖）
    CWA_RADAR_CROP: str = "118.0,20.4,123.6,26.6"  # W,S,E,N
    CWA_RADAR_MAX_PX: int = 1400
    # 農村發展及水土保持署：土石流／大規模崩塌警戒（JSON）與年度圖資（SHP, data.gov.tw 176524/176526/176527）
    ARDSWC_ALERT_URL: str = "https://ls.ardswc.gov.tw/api/LandSlideAlertOpenData"
    ARDSWC_STREAM_SHP_URL: str = "https://data.moa.gov.tw/GetOpenDataFile.aspx?id=J71&FileType=SHP&RID=71084"
    ARDSWC_IMPACT_SHP_URL: str = "https://data.moa.gov.tw/OpenData/GetOpenDataFile.aspx?id=J73&FileType=SHP&RID=71085"
    ARDSWC_LANDSLIDE_SHP_URL: str = "https://data.moa.gov.tw/OpenData/GetOpenDataFile.aspx?id=J74&FileType=SHP&RID=66656"
    OFFICIAL_FILE_CACHE_DAYS: int = 7
    # 交通部 TDX（路況 CCTV 與路況消息）：會員中心申請的 client id / secret
    TDX_CLIENT_ID: str = ""
    TDX_CLIENT_SECRET: str = ""
    TDX_API_BASE: str = "https://tdx.transportdata.tw/api/basic"
    # 水利署 水庫基本資料 / 水庫水情資料（data.gov.tw 32726 / 45501）
    WRA_RESERVOIR_BASIC_DATASET: str = "708a43b0-24dc-40b7-9ed2-fca6a291e7ae"
    WRA_RESERVOIR_REALTIME_DATASET: str = "2be9044c-6e44-4856-aad5-dd108c2e6679"
    # 內政部戶政司 人口統計 datastore
    MOI_RIS_API_BASE: str = "https://www.ris.gov.tw/rs-opendata/api/v1/datastore"
    # 台電 計畫性工作停電（data.gov.tw 26144，每日 ZIP）
    TAIPOWER_OUTAGE_ZIP_URL: str = "https://service.taipower.com.tw/data/opendata/apply/file/d077004/001.zip"
    # NCDR 民生示警公開資料平台 (CAP). The feed requires platform membership;
    # set the CAP JSON/XML feed URL you are entitled to. Empty => unavailable.
    NCDR_CAP_FEED_URL: str = ""

    # Cache TTL for official layers (seconds) — keeps us polite to upstream.
    OFFICIAL_DATA_CACHE_SECONDS: int = 300
    OFFICIAL_DATA_TIMEOUT_SECONDS: int = 12

    # 對外公開網站基底（通知訊息裡的連結會用到）
    WEB_PUBLIC_BASE_URL: str = "http://localhost:3000"

    # LINE 官方帳號推播（module: line_notify）。未設定時記錄為模擬通知。
    LINE_CHANNEL_ACCESS_TOKEN: str = ""

    # ── 派遣／出勤 ───────────────────────────────────────────────────────
    # 路徑規劃：預設公開 OSRM demo server（輕量使用）；正式環境請自架。空字串＝直線估算。
    OSRM_BASE_URL: str = "https://router.project-osrm.org"
    # 出勤通報 webhook（縣府 EOC／CAD 系統接收 JSON）。空＝改走 LINE 或模擬。
    DISPATCH_WEBHOOK_URL: str = ""
    # 出勤模擬：出發準備時間與平均車速（僅在沒有 AVL 即時車位時使用，並標示為模擬）
    DISPATCH_PREP_MINUTES: int = 2
    VEHICLE_SIM_SPEED_KMH: float = 45.0
    # 示範平台：案件仍在「已派員／前往中」時，模擬車輛循環重播整段路程（地圖標示「示範重播」）
    VEHICLE_SIM_LOOP_DEMO: bool = True
    # AVL 即時車位保留時間（秒）：超過即視為離線
    AVL_STALE_SECONDS: int = 180

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        """Managed Postgres hands out postgres:// URLs; SQLAlchemy needs the
        psycopg driver spelled out."""
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+psycopg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def cors_allow_all(self) -> bool:
        return self.CORS_ORIGINS.strip() == "*"

    @property
    def default_cluster_policy(self) -> dict:
        return {
            "required_unique_reporters": self.CLUSTER_REQUIRED_UNIQUE_REPORTERS,
            "radius_meters": self.CLUSTER_RADIUS_METERS,
            "time_window_minutes": self.CLUSTER_TIME_WINDOW_MINUTES,
            "count_anonymous_reporters": True,
        }


settings = Settings()
