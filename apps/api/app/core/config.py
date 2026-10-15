from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # No default on purpose: the connection string carries credentials, so it
    # must come from the environment (docker-compose / the managed host).
    DATABASE_URL: str

    # Optional service key: when set, a request carrying a matching X-API-Key
    # header is treated as a system-administrator service call (scripts, CI).
    # Staff use accounts (AUTH_*) instead.
    ADMIN_API_KEY: str = ""

    # ── 登入與權限 ──────────────────────────────────────────────────────
    # true = 政府後台端點一律需要登入（正式環境必須開啟）。false 只供本機開發／
    # 自動化測試：未帶權杖的請求視為具備全部權限的「開發模式」使用者。
    AUTH_REQUIRED: bool = True
    # 簽發登入權杖用的密鑰。未設定時僅開發環境可用（啟動時以臨時密鑰代替，重啟即失效）；
    # ENVIRONMENT 非 development 時未設定會拒絕啟動。
    AUTH_SECRET: str = ""
    AUTH_TOKEN_HOURS: int = 12
    # 連續登入失敗幾次後鎖定、鎖定幾分鐘
    AUTH_MAX_FAILED_ATTEMPTS: int = 5
    AUTH_LOCK_MINUTES: int = 15
    AUTH_MIN_PASSWORD_LENGTH: int = 10
    # true = 管理者建立或重設的密碼，使用者首次登入必須先變更。測試階段預設關閉，
    # 使用者可自行到「帳號設定」變更密碼。
    AUTH_FORCE_PASSWORD_CHANGE: bool = False
    # 首次啟動且資料庫沒有任何帳號時，以此建立系統管理者（建立後請立即變更密碼）
    INITIAL_ADMIN_USERNAME: str = "admin"
    INITIAL_ADMIN_PASSWORD: str = ""

    # 通報者聯絡資料（稱呼、電話、Email）AES-256-GCM 加密保存的金鑰：32 bytes 的
    # URL-safe base64，或任一足夠長的隨機字串（例：openssl rand -hex 32）。
    # 未設定時由 AUTH_SECRET 衍生；正式環境務必設定並妥善保管，遺失將無法解密既有資料。
    DATA_ENCRYPTION_KEY: str = ""

    # ── 濫用防護：公開端寫入 API 的每 IP 頻率限制（次／分鐘） ──────────────
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REPORTS_PER_MINUTE: int = 10
    RATE_LIMIT_UPLOADS_PER_MINUTE: int = 30
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 10
    RATE_LIMIT_LAYERS_PER_MINUTE: int = 60
    # 反向代理後方時才可開啟：信任 X-Forwarded-For 的最後一個位址（最接近本服務的
    # 那一跳）。預設關閉，避免用戶端自行偽造標頭繞過頻率限制。
    TRUST_FORWARDED_FOR: bool = False

    # Comma-separated allowed CORS origins, or "*" for any origin
    # (credentials are disabled automatically in that case).
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001"
    )

    APP_NAME: str = "AidFlow API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    # Demo mode: enables the demo scenario seeder (/v1/demo/*). Off by default so
    # a production deployment cannot inject synthetic reports into a live platform.
    DEMO_MODE: bool = False
    # 示範情境下，生成出來的平台不累積：只保留最新 N 個（0 = 全部保留）。
    # 內建的南投示範平台永遠保留。
    DEMO_KEEP_GENERATED: int = 1

    # ── Deterministic clustering defaults (per-platform policy overrides these).
    CLUSTER_REQUIRED_UNIQUE_REPORTERS: int = 2
    CLUSTER_RADIUS_METERS: int = 100
    CLUSTER_TIME_WINDOW_MINUTES: int = 60

    # ── Media storage for citizen photos (local filesystem abstraction).
    MEDIA_ROOT: str = "./media"
    MEDIA_MAX_BYTES: int = 8 * 1024 * 1024

    # Pepper for hashing reporter identities (device key / contact) into an
    # opaque reporter_key. Change per deployment.
    # 未設定時僅開發環境可用（啟動時產生臨時鹽）；正式環境未設定會拒絕啟動。
    REPORTER_HASH_SALT: str = ""

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
    # 對外 API 基底（照片等公開檔案的完整網址，例如上報 EMIC 時附上照片連結）
    API_PUBLIC_BASE_URL: str = "http://localhost:8000"

    # ── LINE BOT：新通報推播至縣府 LINE 群組 ────────────────────────────
    # Messaging API 的 Channel access token；未設定時通知記錄為「模擬」。
    LINE_CHANNEL_ACCESS_TOKEN: str = ""
    # Channel secret：驗證 LINE webhook 簽章（群組綁定用）。未設定時 webhook 拒收。
    LINE_CHANNEL_SECRET: str = ""

    # ── Email：通報民眾的案件進度通知 ───────────────────────────────────
    # 未設定 SMTP_HOST 時通知記錄為「模擬」，不會真的寄出。
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True
    SMTP_FROM: str = "AidFlow 災情通報 <no-reply@localhost>"
    SMTP_TIMEOUT_SECONDS: int = 10

    # ── EMIC（內政部消防署緊急應變管理資訊雲端服務系統）介接 ──────────────
    # 介接規格尚未由消防署提供。未設定 EMIC_SUBMIT_URL 時採「人工登錄」：承辦
    # 於 EMIC 建立案件後，回填 EMIC 案號與處理狀態。設定後系統會以 JSON POST
    # 將欄位對照（app/domain/emic.py）後的案件資料送至該端點。
    EMIC_SUBMIT_URL: str = ""
    EMIC_API_TOKEN: str = ""
    EMIC_TIMEOUT_SECONDS: int = 15

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
    def is_development(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in {"development", "test", "local"}

    def startup_problems(self) -> list[str]:
        """Settings that must never reach a non-development deployment."""
        if self.is_development:
            return []
        problems: list[str] = []
        if not self.AUTH_SECRET.strip():
            problems.append("AUTH_SECRET 未設定（登入權杖簽章密鑰）")
        elif len(self.AUTH_SECRET.strip()) < 32:
            problems.append("AUTH_SECRET 長度不足 32 字元")
        if not self.DATA_ENCRYPTION_KEY.strip():
            problems.append("DATA_ENCRYPTION_KEY 未設定（通報者聯絡資料加密金鑰）")
        if not self.REPORTER_HASH_SALT.strip():
            problems.append("REPORTER_HASH_SALT 未設定（通報者去識別化雜湊鹽）")
        if not self.AUTH_REQUIRED:
            problems.append("AUTH_REQUIRED 為 false（後台端點將不需登入）")
        if self.cors_allow_all:
            problems.append("CORS_ORIGINS 為 *（請列出實際的前端網域）")
        return problems

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
