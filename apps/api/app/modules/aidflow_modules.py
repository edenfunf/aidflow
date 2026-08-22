"""The AidFlow module catalogue.

Every id here is stable: platforms persist module ids, the frontend switches
on them, and tests assert on them. Adding a capability = adding a spec here
(and implementing it); the planner picks it up automatically.
"""
from __future__ import annotations

from app.modules.base import ModuleSpec
from app.modules.registry import registry

WATER = ("typhoon", "heavy_rain", "flood", "barrier_lake", "landslide")
SLOPE = ("heavy_rain", "landslide", "typhoon", "earthquake")
QUAKE = ("earthquake",)

MODULES: tuple[ModuleSpec, ...] = (
    # ── reporting ────────────────────────────────────────────────────────
    ModuleSpec("report_form", "災情通報表單", "行動優先的民眾通報表單：發生什麼事、在哪裡、照片、描述、我是誰。",
               "reporting", surfaces=("public",), core=True),
    ModuleSpec("report_category", "動態災情類別", "依災害情境只顯示相關的災情類別（例如豪雨不顯示瓦斯外洩）。",
               "reporting", surfaces=("public",), core=True, dependencies=("report_form",)),
    ModuleSpec("geo_location", "定位與地圖選點", "GPS 自動定位或在地圖上點選災情位置；無座標的通報不進入聚類。",
               "reporting", surfaces=("public",), core=True, dependencies=("report_form",)),
    ModuleSpec("photo_upload", "現場照片上傳", "現場照片附加到通報；政府端可補前／後對照照片。",
               "reporting", dependencies=("report_form",)),
    ModuleSpec("reporter_role", "回報者身分", "民眾／村里長／防災士／志工／社區組織；受訓身分的回報在分級時加權。",
               "reporting", surfaces=("public",), dependencies=("report_form",)),
    # ── processing ───────────────────────────────────────────────────────
    ModuleSpec("severity_triage", "嚴重度自動分級", "依災情類別與回報者身分進行規則式分級（不使用模型）。",
               "processing", module_type="processor", surfaces=("console",), core=True),
    ModuleSpec("geo_cluster", "地理聚類引擎", "以距離、時間窗與相近類別把通報聚成同一災點（deterministic）。",
               "processing", module_type="processor", surfaces=("console",), core=True),
    ModuleSpec("duplicate_report_merge", "重複通報合併", "同一回報者的重複送出只計一次；同災點多筆通報合併呈現。",
               "processing", module_type="processor", surfaces=("console",), core=True,
               dependencies=("geo_cluster",)),
    ModuleSpec("two_report_trigger", "多人回報成案門檻", "同地點達到 N 位不同回報者即自動成案（預設 2 人／100 公尺／60 分鐘，可調）。",
               "processing", module_type="processor", surfaces=("console",), core=True,
               dependencies=("geo_cluster", "duplicate_report_merge"),
               default_config={"required_unique_reporters": 2, "radius_meters": 100,
                               "time_window_minutes": 60}),
    ModuleSpec("incident_case_creation", "正式案件建立", "門檻達成或人工確認後建立正式案件，進入待派工。",
               "processing", module_type="processor", surfaces=("console",), core=True,
               dependencies=("two_report_trigger",)),
    # ── dispatch ─────────────────────────────────────────────────────────
    ModuleSpec("case_status", "案件狀態機", "待派工→已派員→前往中→抵達→處理中→完成→結案，只允許定義的轉換。",
               "dispatch", surfaces=("console",), core=True),
    ModuleSpec("case_dispatch", "派工", "縣府確認後指派處理單位與人員，公開端同步顯示已派員。",
               "dispatch", surfaces=("console",), core=True, dependencies=("case_status",)),
    ModuleSpec("case_assignment", "處理單位指派", "指定負責單位、帶隊人員與聯絡方式（內部可見）。",
               "dispatch", surfaces=("console",), dependencies=("case_dispatch",)),
    # ── visualization: core map + data layers ────────────────────────────
    ModuleSpec("incident_map", "互動災情地圖", "公開端與後台共用的大型互動地圖，圖層可開關、可依區域／時間／類別／狀態篩選。",
               "visualization", core=True),
    ModuleSpec("citizen_report_layer", "民眾通報圖層", "去識別化的民眾通報點（座標粗化至約 100 公尺）。",
               "visualization", module_type="layer", layer_key="citizen_reports", core=True),
    ModuleSpec("incident_case_layer", "正式案件圖層", "正式案件位置、嚴重度與處理狀態。",
               "visualization", module_type="layer", layer_key="incident_cases", core=True),
    ModuleSpec("report_cluster_layer", "多人回報聚類圖層", "同災點多人回報以聚類呈現，不堆疊大量 marker。",
               "visualization", module_type="layer", layer_key="report_clusters", core=True),
    ModuleSpec("heatmap_layer", "災情熱區圖層", "通報密度熱區，快速看出哪裡最嚴重。",
               "visualization", module_type="layer", layer_key="heatmap"),
    ModuleSpec("government_processing_layer", "政府處理中圖層", "只顯示已派員／處理中的案件，讓民眾看到政府正在處理什麼。",
               "visualization", module_type="layer", layer_key="government_processing"),
    ModuleSpec("flooding_layer", "積淹水圖層", "積淹水相關通報與案件。", "visualization",
               module_type="layer", layer_key="flooding", applicable_hazards=WATER),
    ModuleSpec("road_damage_layer", "道路災害圖層", "道路坍方、中斷、橋梁受損、倒木。", "visualization",
               module_type="layer", layer_key="road_damage"),
    ModuleSpec("landslide_layer", "土石流圖層", "土石流與邊坡崩塌通報。", "visualization",
               module_type="layer", layer_key="landslide", applicable_hazards=SLOPE),
    ModuleSpec("trapped_people_layer", "人員受困圖層", "人員受困與醫療需求，永遠置頂顯示。", "visualization",
               module_type="layer", layer_key="trapped_people"),
    ModuleSpec("building_damage_layer", "建築損害圖層", "建物損害、火災、瓦斯外洩。", "visualization",
               module_type="layer", layer_key="building_damage", applicable_hazards=QUAKE + ("typhoon",)),
    ModuleSpec("lifeline_layer", "維生管線圖層", "停電、停水通報。", "visualization",
               module_type="layer", layer_key="lifeline", applicable_hazards=("typhoon", "earthquake")),
    # ── visualization: official layers (fed by connectors) ───────────────
    ModuleSpec("shelter_layer", "避難收容處所圖層", "內政部消防署避難收容處所點位檔（依縣市篩選）。",
               "visualization", module_type="layer", layer_key="shelter", source="moi_shelter_connector",
               dependencies=("moi_shelter_connector",)),
    ModuleSpec("fire_station_layer", "消防單位圖層", "南投縣政府開放資料：消防局各單位點位。",
               "visualization", module_type="layer", layer_key="fire_station",
               source="nantou_open_data_connector", dependencies=("nantou_open_data_connector",)),
    ModuleSpec("official_alert_layer", "官方警戒圖層", "中央氣象署天氣特報與 NCDR CAP 示警。",
               "visualization", module_type="layer", layer_key="official_alert", source="cwa_connector",
               dependencies=("cwa_connector",)),
    ModuleSpec("rainfall_layer", "雨量圖層", "中央氣象署自動雨量站即時觀測（O-A0002-001）。",
               "visualization", module_type="layer", layer_key="rainfall", source="cwa_connector",
               applicable_hazards=WATER, dependencies=("cwa_connector",)),
    ModuleSpec("water_layer", "河川水情圖層", "經濟部水利署河川水位站即時水位與警戒水位。",
               "visualization", module_type="layer", layer_key="water", source="wra_connector",
               applicable_hazards=WATER, dependencies=("wra_connector",)),
    ModuleSpec("radar_layer", "雷達回波圖層", "中央氣象署雷達整合回波透明圖層（O-A0058-005），可回放最近兩小時。",
               "visualization", module_type="layer", layer_key="radar", source="cwa_connector",
               applicable_hazards=WATER, dependencies=("cwa_connector",)),
    ModuleSpec("debris_flow_layer", "土石流潛勢溪流圖層", "農村發展及水土保持署潛勢溪流、影響範圍與即時紅黃警戒。",
               "visualization", module_type="layer", layer_key="debris_flow", source="ardswc_connector",
               applicable_hazards=SLOPE, dependencies=("ardswc_connector",)),
    ModuleSpec("landslide_zone_layer", "大規模崩塌潛勢區圖層", "農村發展及水土保持署大規模崩塌潛勢區與警戒。",
               "visualization", module_type="layer", layer_key="landslide_zone", source="ardswc_connector",
               applicable_hazards=SLOPE, dependencies=("ardswc_connector",)),
    ModuleSpec("road_traffic_layer", "道路路況與 CCTV 圖層", "交通部 TDX 路況監視器即時影像與封閉／坍方路況消息。",
               "visualization", module_type="layer", layer_key="road_traffic", source="tdx_connector",
               dependencies=("tdx_connector",)),
    ModuleSpec("reservoir_layer", "水庫水情圖層", "水利署水庫蓄水率、水位與洩洪狀態（位置為鄉鎮示意）。",
               "visualization", module_type="layer", layer_key="reservoir", source="wra_connector",
               applicable_hazards=WATER, dependencies=("wra_connector",)),
    ModuleSpec("population_layer", "人口分布圖層", "內政部戶政司各鄉鎮人口，用於受影響人口估算與人口加權統計。",
               "visualization", module_type="layer", layer_key="population", source="moi_population_connector",
               dependencies=("moi_population_connector",)),
    ModuleSpec("power_outage_layer", "計畫停電圖層", "台電每日計畫性工作停電公告，依鄉鎮彙整。",
               "visualization", module_type="layer", layer_key="power_outage", source="taipower_connector",
               applicable_hazards=("typhoon", "earthquake"), dependencies=("taipower_connector",), default_enabled=False),
    # ── official data connectors ─────────────────────────────────────────
    ModuleSpec("nantou_open_data_connector", "南投縣政府開放資料", "data.nantou.gov.tw CKAN DataStore 介接。",
               "official_data", module_type="connector", surfaces=("console",)),
    ModuleSpec("moi_shelter_connector", "消防署避難收容處所", "data.gov.tw 73242 避難收容處所點位檔。",
               "official_data", module_type="connector", surfaces=("console",)),
    ModuleSpec("cwa_connector", "中央氣象署開放資料", "雨量站觀測、天氣特報（需 CWA_API_KEY）。",
               "official_data", module_type="connector", surfaces=("console",)),
    ModuleSpec("wra_connector", "水利署水利資料開放平台", "河川水位測站站況 + 即時水位（公開，無需金鑰）。",
               "official_data", module_type="connector", surfaces=("console",), applicable_hazards=WATER),
    ModuleSpec("ncdr_connector", "NCDR 民生示警 (CAP)", "CAP 示警介接；需平台會員授權的 feed URL。",
               "official_data", module_type="connector", surfaces=("console",), default_enabled=False),
    ModuleSpec("ardswc_connector", "農村發展及水土保持署 土石流防災資訊", "潛勢溪流／大規模崩塌圖資（SHP）與紅黃警戒 JSON（公開，無需金鑰）。",
               "official_data", module_type="connector", surfaces=("console",), applicable_hazards=SLOPE),
    ModuleSpec("tdx_connector", "交通部 TDX 路況", "路況 CCTV 與路況消息（需 TDX_CLIENT_ID / TDX_CLIENT_SECRET）。",
               "official_data", module_type="connector", surfaces=("console",)),
    ModuleSpec("moi_population_connector", "內政部戶政司人口統計", "各村里人口數 datastore（公開，無需金鑰）。",
               "official_data", module_type="connector", surfaces=("console",)),
    ModuleSpec("taipower_connector", "台電計畫性停電", "每日計畫性工作停電 ZIP（公開，無需金鑰）。",
               "official_data", module_type="connector", surfaces=("console",), applicable_hazards=("typhoon", "earthquake"), default_enabled=False),
    # ── public transparency ──────────────────────────────────────────────
    ModuleSpec("public_timeline", "公開處理時間軸", "每個案件從第一筆通報到處理完成的完整時間軸，由真實事件產生。",
               "public_transparency", surfaces=("public",), core=True),
    ModuleSpec("status_progress", "處理進度顯示", "公開端顯示案件目前處理階段與進度條。",
               "public_transparency", surfaces=("public",), core=True),
    ModuleSpec("public_case_list", "公開案件清單", "最新災情與案件列表，可依類別／狀態／鄉鎮篩選。",
               "public_transparency", surfaces=("public",), core=True),
    # ── analytics ────────────────────────────────────────────────────────
    ModuleSpec("incident_statistics", "災情統計", "目前災情／處理中／已完成／高風險與各鄉鎮分布。",
               "analytics", core=True),
    ModuleSpec("trend_visualization", "災情趨勢", "近 24 小時通報與成案趨勢，判斷情勢是否惡化。",
               "analytics"),
    # ── privacy ──────────────────────────────────────────────────────────
    ModuleSpec("privacy_mask", "位置與地址遮罩", "公開端座標粗化、地址只保留路段／村里。",
               "privacy", module_type="processor", core=True),
    ModuleSpec("personal_data_redaction", "個資去識別化", "姓名、電話、Email、IP 絕不出現在公開 API。",
               "privacy", module_type="processor", core=True),
    # ── notification ─────────────────────────────────────────────────────
    ModuleSpec("line_notify", "LINE 推播通知", "成案、派工、完成時推播 LINE 官方帳號（未設定憑證時記錄為模擬）。",
               "notification", module_type="action", surfaces=("console",), default_enabled=False),
)


def register() -> None:
    for spec in MODULES:
        registry.register(spec)
