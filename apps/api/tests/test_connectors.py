"""Connector normalisers (offline) and the layer service's fallback statuses."""
from __future__ import annotations

import pytest

from app.connectors import cwa, moi_shelters, nantou_open_data, ncdr, wra
from app.connectors.base import ConnectorDisabled, ConnectorError
from app.services import official_data_service


def test_nantou_fire_stations_skip_rows_without_coordinates():
    feats = nantou_open_data.map_fire_stations(nantou_open_data.SAMPLE_FIRE_STATIONS)
    assert len(feats) == 2
    f = feats[0]
    assert f["layer"] == "fire_station" and f["source"] == "nantou_open_data"
    assert f["coordinates"] == [120.679225, 23.945575]  # [lon, lat]
    assert f["properties"]["name"] == "第一大隊" and f["properties"]["kind"] == "大隊"


def test_moi_shelters_filter_by_county_and_drop_manager_name():
    rows = moi_shelters.parse_csv(moi_shelters.SAMPLE_CSV)
    feats = moi_shelters.map_shelters(rows, "南投縣")
    assert len(feats) == 2
    p = feats[0]["properties"]
    assert p["county"] == "南投縣" and p["town"] == "信義鄉" and p["capacity"] == 150
    assert "土石流" in p["hazards"]
    assert "伍宗信" not in str(p)
    assert len(moi_shelters.map_shelters(rows, None)) == 3
    assert moi_shelters.map_shelters(rows, "花蓮縣") == []


def test_wra_join_and_alert_status():
    feats = wra.map_water_levels(wra.SAMPLE_STATIONS, wra.SAMPLE_LEVELS, None)
    names = {f["properties"]["name"]: f for f in feats}
    assert "金山" not in names  # 已廢 station dropped
    jin = names["新磺溪橋(即時)"]["properties"]
    assert jin["water_level_m"] == 1.89 and jin["status"] == "normal"
    ai = names["愛國橋"]["properties"]
    assert ai["water_level_m"] == 449.55  # latest reading wins
    assert ai["status"] == "alert2" and ai["severity"] == "high"
    only_nantou = wra.map_water_levels(wra.SAMPLE_STATIONS, wra.SAMPLE_LEVELS, "南投縣")
    assert [f["properties"]["name"] for f in only_nantou] == ["愛國橋"]
    assert wra.alert_status(None, 1, 2, 3) == "unknown"
    assert wra.alert_status(10, 5.8, 4.6, None) == "alert1"


def test_cwa_rainfall_filters_county_and_classifies():
    feats = cwa.map_rainfall(cwa.SAMPLE_RAINFALL, "南投縣")
    assert {f["properties"]["name"] for f in feats} == {"廬山", "日月潭"}
    lushan = next(f for f in feats if f["properties"]["name"] == "廬山")["properties"]
    assert lushan["level"] == "heavy" and lushan["severity"] == "high"
    assert lushan["rain_24h_mm"] == 268.0
    sun = next(f for f in feats if f["properties"]["name"] == "日月潭")["properties"]
    assert sun["rain_now_mm"] is None  # -99 => missing
    assert sun["level"] == "moderate"
    assert feats[0]["coordinates"] == [121.1761, 24.0289]  # WGS84 picked over TWD67


def test_cwa_warnings_and_earthquakes():
    warns = cwa.map_warnings(cwa.SAMPLE_WARNINGS, "南投縣")
    assert len(warns) == 1 and warns[0]["properties"]["phenomena"] == "豪雨"
    assert cwa.map_warnings(cwa.SAMPLE_WARNINGS, "台北市") == []
    eq = cwa.map_earthquakes(cwa.SAMPLE_EARTHQUAKE)
    assert eq[0]["properties"]["severity"] == "high" and eq[0]["properties"]["magnitude"] == 5.2


def test_cwa_without_key_is_disabled_not_fake(monkeypatch):
    monkeypatch.setattr(cwa.settings, "CWA_API_KEY", "")
    with pytest.raises(ConnectorDisabled):
        cwa.fetch_rainfall("南投縣")


def test_ncdr_cap_polygon_and_county_filter():
    feats = ncdr.map_cap(ncdr.SAMPLE_CAP, "南投縣")
    assert len(feats) == 2
    flood = feats[0]
    assert flood["type"] == "Polygon" and flood["properties"]["severity"] == "high"
    assert flood["coordinates"][0][0] == [120.94, 23.94]  # lon,lat + ring closed
    assert flood["coordinates"][0][0] == flood["coordinates"][0][-1]
    slope = feats[1]
    assert slope["type"] == "Point" and "仁愛鄉" in slope["properties"]["area"]
    assert len(ncdr.map_cap(ncdr.SAMPLE_CAP, None)) == 3


def test_ncdr_cap_xml_parsing():
    xml = """<?xml version="1.0"?>
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
      <identifier>X-1</identifier><sent>2026-08-21T10:00:00+08:00</sent>
      <info><event>淹水警戒</event><severity>Severe</severity><headline>南投縣埔里鎮淹水警戒</headline>
        <area><areaDesc>南投縣埔里鎮</areaDesc></area></info>
    </alert>"""
    parsed = ncdr.parse_cap_xml(xml)
    feats = ncdr.map_cap(parsed, "南投縣")
    assert len(feats) == 1 and feats[0]["id"] == "ncdr:X-1#0"
    with pytest.raises(ConnectorError):
        ncdr.parse_cap_xml("<not xml")


class _P:
    """Minimal platform stand-in for the layer service."""

    def __init__(self, layers, county="南投縣", hazards=("heavy_rain",)):
        self.layers = layers
        self.county = county
        self.hazards = list(hazards)


def test_layer_service_reports_disabled_unavailable_and_not_enabled(monkeypatch):
    official_data_service.clear_cache()
    monkeypatch.setattr(cwa.settings, "CWA_API_KEY", "")
    monkeypatch.setattr(ncdr.settings, "NCDR_CAP_FEED_URL", "")
    p = _P(["rainfall", "official_alert", "shelter"])
    rain = official_data_service.get_layer(p, "rainfall")
    assert rain["status"] == "disabled" and rain["features"] == [] and "CWA_API_KEY" in rain["detail"]
    alert = official_data_service.get_layer(p, "official_alert")
    assert alert["status"] == "disabled"

    def boom(county):
        raise ConnectorError("上游回應 HTTP 503")

    monkeypatch.setitem(official_data_service._LAYER_FETCHERS, "shelter", [("moi_shelter_connector", boom)])
    shelter = official_data_service.get_layer(p, "shelter")
    assert shelter["status"] == "unavailable" and "503" in shelter["detail"]
    assert official_data_service.get_layer(p, "water")["status"] == "not_enabled"
    # cached on second call
    assert official_data_service.get_layer(p, "shelter")["cached"] is True
    official_data_service.clear_cache()


def test_layer_service_ok_path_with_stubbed_fetcher(monkeypatch):
    official_data_service.clear_cache()
    rows = moi_shelters.parse_csv(moi_shelters.SAMPLE_CSV)
    monkeypatch.setitem(official_data_service._LAYER_FETCHERS, "shelter",
                        [("moi_shelter_connector", lambda county: moi_shelters.map_shelters(rows, county))])
    p = _P(["shelter"])
    out = official_data_service.get_layer(p, "shelter")
    assert out["status"] == "ok" and out["count"] == 2 and out["attribution"]
    statuses = official_data_service.layer_statuses(p)
    assert statuses[0]["status"] == "ok"
    official_data_service.clear_cache()


def test_connector_status_listing_is_honest_about_keys():
    items = {c["id"]: c for c in official_data_service.connector_statuses()}
    assert items["cwa_connector"]["requires_key"] and items["cwa_connector"]["key_env"] == "CWA_API_KEY"
    assert not items["wra_connector"]["requires_key"] and items["wra_connector"]["live_enabled"]
    assert items["ncdr_connector"]["status"] == "disabled"
