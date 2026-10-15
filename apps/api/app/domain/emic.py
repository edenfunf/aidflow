"""EMIC 欄位對照（暫定）.

內政部消防署 EMIC 的介接規格與欄位定義尚待縣府協助取得。在規格確認前，
本表定義「本系統欄位 → 上報資料鍵值」的暫定對照，作為 JSON 上報端點
（EMIC_SUBMIT_URL）的內容，以及後台人工登錄時的參考。取得正式規格後，
只需修改此表與 connectors/emic.py，其餘流程不變。

The mapping is deliberately data, not code, so replacing it with the real
specification is a one-file change.
"""
from __future__ import annotations

# (上報鍵值, 說明, 本系統來源)
FIELD_MAP: tuple[tuple[str, str, str], ...] = (
    ("source_system", "資料來源系統", "固定值 AidFlow"),
    ("source_case_no", "來源案號", "incident_cases.case_number"),
    ("county", "縣市", "platforms.county"),
    ("town", "鄉鎮市區", "incident_cases.town"),
    ("location", "災害地點描述", "incident_cases.location_label"),
    ("lat", "緯度（WGS84）", "incident_cases.lat"),
    ("lon", "經度（WGS84）", "incident_cases.lon"),
    ("category", "災情類別", "incident_cases.category（本系統分類代碼）"),
    ("category_label", "災情類別名稱", "incident_cases.category 對應中文"),
    ("severity", "嚴重程度", "incident_cases.severity（極高／高／中／低）"),
    ("occurred_at", "發生（首報）時間", "incident_cases.created_at"),
    ("reported_count", "通報筆數", "incident_cases.report_count"),
    ("reporter_count", "不同回報者人數", "incident_cases.unique_reporter_count"),
    ("description", "災情摘要", "各筆通報描述（已去識別化）"),
    ("photos", "現場照片連結", "report_photos 公開網址"),
    ("disaster_name", "災害事件名稱", "platforms.name"),
)

# EMIC 案件在本系統顯示的處理狀態文字（暫定選項；可自由輸入）
STATUS_SUGGESTIONS: tuple[str, ...] = ("已受理", "處理中", "已派員處理", "持續監控", "已處理完成", "已結案")
