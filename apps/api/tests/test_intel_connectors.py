"""Second-wave official data connectors: every normaliser is pure and tested
against representative payloads (shapes per the published docs / probed
responses). No network."""
from __future__ import annotations

from app.connectors import ardswc, cwa, moi_population, taipower, tdx, wra


def test_ardswc_alert_index_and_streams():
    by_stream, by_zone = ardswc.index_alerts(ardswc.SAMPLE_ALERTS)
    assert by_stream["投縣DF124"]["alert"] == "red" and by_stream["投縣DF001"]["alert"] == "yellow"
    assert by_zone["高市LL003"]["alert"] == "red" and by_zone["DS145"]["alert"] == "red"
    feats = ardswc.map_streams(ardswc.SAMPLE_STREAM_ROWS, by_stream, "南投縣")
    assert len(feats) == 1
    f = feats[0]
    assert f["type"] == "LineString" and f["layer"] == "debris_flow" and len(f["coordinates"]) == 3
    assert f["properties"]["alert"] == "red" and f["properties"]["severity"] == "critical" and f["properties"]["road"] == "投26線"
    # no alert → severity follows the published risk class
    feats_all = ardswc.map_streams(ardswc.SAMPLE_STREAM_ROWS, {}, None)
    assert {x["properties"]["severity"] for x in feats_all} == {"medium", "low"}
    zones = ardswc.map_landslide_zones(ardswc.SAMPLE_ZONE_ROWS, {"投縣LL001": {"alert": "yellow", "alert_time": "t"}}, "南投縣")
    assert zones[0]["type"] == "Polygon" and zones[0]["properties"]["alert"] == "yellow" and zones[0]["properties"]["households"] == 12
    # alerts for streams missing from the shapefile become township markers
    pts = ardswc.map_alert_points(ardswc.SAMPLE_ALERTS, "南投縣")
    assert {p["properties"]["debris_no"] for p in pts} == {"投縣DF124", "投縣DF001"}


def test_ardswc_reads_real_shapefile_format(tmp_path):
    """A tiny shapefile written with pyshp round-trips through the reader
    (TWD97 → WGS84)."""
    import shapefile

    w = shapefile.Writer(str(tmp_path / "s"), shapeType=shapefile.POLYLINE, encoding="utf-8")
    w.field("Debrisno", "C"); w.field("County01", "C"); w.field("Risk", "C")
    w.line([[(240000.0, 2650000.0), (240500.0, 2650400.0)]])
    w.record("投縣DF999", "南投縣", "高")
    w.close()
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for ext in ("shp", "shx", "dbf"):
            z.write(tmp_path / f"s.{ext}", f"s.{ext}")
    rows, kind = ardswc.read_shapefile(buf.getvalue())
    assert kind == "POLYLINE" and rows[0]["record"]["Debrisno"] == "投縣DF999"
    lon, lat = rows[0]["parts"][0][0]
    assert 120.5 < lon < 121.0 and 23.8 < lat < 24.1  # central Taiwan


def test_tdx_cctv_and_news_mapping():
    cams = tdx.map_cctv(tdx.SAMPLE_CCTV, "南投縣", "highway")
    assert len(cams) == 1 and cams[0]["properties"]["image_url"].endswith("14a018.jpg") and cams[0]["properties"]["road"] == "台14甲線"
    news = tdx.map_news(tdx.SAMPLE_NEWS, "南投縣", "highway")
    assert len(news) == 1 and news[0]["properties"]["status"] == "closure" and news[0]["properties"]["indicative"] is True
    assert tdx.map_news(tdx.SAMPLE_NEWS, "南投縣", "city")  # city feed is kept verbatim
    assert tdx._city("南投縣") == "NantouCounty" and tdx._city("台中市") == "Taichung"


def test_tdx_is_disabled_without_credentials(monkeypatch):
    from app.core.config import settings
    from app.connectors.base import ConnectorDisabled
    import pytest

    monkeypatch.setattr(settings, "TDX_CLIENT_ID", "")
    monkeypatch.setattr(settings, "TDX_CLIENT_SECRET", "")
    with pytest.raises(ConnectorDisabled):
        tdx.fetch_road_traffic("南投縣")


def test_population_aggregates_to_towns():
    towns = moi_population.aggregate_towns(moi_population.SAMPLE_ROWS, "南投縣")
    assert [t["town"] for t in towns] == ["埔里鎮", "仁愛鄉"]
    renai = next(t for t in towns if t["town"] == "仁愛鄉")
    assert renai["population"] == 3300 and renai["villages"] == 2 and renai["indigenous_mountain"] == 2160
    feats = moi_population.map_population(moi_population.SAMPLE_ROWS, "南投縣", "11506")
    assert len(feats) == 2 and abs(sum(f["properties"]["share"] for f in feats) - 1) < 0.01
    assert feats[0]["properties"]["county_population"] == 6700
    assert moi_population.roc_months(__import__("datetime").date(2026, 8, 22))[:2] == ["11508", "11507"]


def test_taipower_outages_by_town():
    feats = taipower.map_outages(taipower.SAMPLE_ROWS, "南投縣")
    assert len(feats) == 1 and feats[0]["properties"]["town"] == "埔里鎮" and feats[0]["properties"]["count"] == 2
    assert feats[0]["properties"]["items"][0]["work"] == "改良工程"
    assert taipower.map_outages(taipower.SAMPLE_ROWS, None) == []


def test_wra_reservoirs_join_latest_reading():
    feats = wra.map_reservoirs(wra.SAMPLE_RESERVOIR_BASIC, wra.SAMPLE_RESERVOIR_REALTIME, "南投縣")
    by = {f["properties"]["name"]: f["properties"] for f in feats}
    assert set(by) == {"霧社水庫", "日月潭水庫"}
    assert by["霧社水庫"]["status"] == "releasing" and by["霧社水庫"]["storage_pct"] == 95.9
    assert by["日月潭水庫"]["effective_storage"] == 9800.0  # newest observation wins
    assert by["日月潭水庫"]["town"] == "魚池鄉" and by["日月潭水庫"]["indicative"] is True


def test_cwa_radar_product_parsing(monkeypatch):
    prod = cwa.radar_product(cwa.SAMPLE_RADAR_FILE)
    assert prod["url"].endswith("O-A0058-005.png") and prod["stamp"] == "202608221200"
    assert prod["bounds"] == (115.0, 17.75, 126.5, 29.25)
    from app.core.config import settings
    from app.connectors.base import ConnectorDisabled
    import pytest

    monkeypatch.setattr(settings, "CWA_API_KEY", "")
    with pytest.raises(ConnectorDisabled):
        cwa.fetch_radar_frames()


def test_layers_are_registered():
    from app.services import official_data_service as ods
    from app.modules import registry

    for key in ("radar", "debris_flow", "landslide_zone", "road_traffic", "reservoir", "population", "power_outage"):
        assert key in ods.OFFICIAL_LAYERS and registry.layer_by_key(key) is not None
    ids = {c["id"] for c in ods.connector_statuses()}
    assert {"ardswc_connector", "tdx_connector", "moi_population_connector", "taipower_connector"} <= ids
