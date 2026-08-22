from __future__ import annotations

from app.services import scenario_rules

BRIEF = (
    "南投縣仁愛鄉因颱風帶來連續豪雨，多處山區道路可能發生坍方、土石流與積淹水，"
    "部分偏遠部落可能交通中斷，希望民眾、村里長、防災士與志工都可以共同回報災情。"
)


def test_parse_brief_extracts_region_hazards_impacts_roles():
    out = scenario_rules.parse_brief(BRIEF)
    assert out["county"] == "南投縣"
    assert out["towns"] == ["仁愛鄉"]
    assert {"typhoon", "heavy_rain", "landslide", "flood"} <= set(out["hazards"])
    assert {"road_collapse", "landslide", "flooding", "road_blocked"} <= set(out["impacts"])
    assert out["reporter_roles"] == ["citizen", "village_chief", "disaster_officer", "volunteer"]
    assert "雨量" in out["data_needs"] and "避難收容處所" in out["data_needs"]
    assert out["name"].startswith("南投縣仁愛鄉")


def test_parse_brief_handles_multiple_towns_and_short_forms():
    out = scenario_rules.parse_brief("南投信義、埔里、國姓和水里都有災情")
    assert out["county"] == "南投縣"
    assert set(out["towns"]) == {"信義鄉", "埔里鎮", "國姓鄉", "水里鄉"}


def test_parse_brief_does_not_confuse_street_names_with_towns():
    out = scenario_rules.parse_brief("南投市仁愛路積水嚴重，民眾回報")
    assert "仁愛鄉" not in out["towns"]
    assert out["towns"] == ["南投市"]
    assert "flood" in out["hazards"]


def test_parse_brief_infers_hazard_from_impacts_and_falls_back_gracefully():
    out = scenario_rules.parse_brief("花蓮市區多棟建物倒塌，有人受困")
    assert out["county"] == "花蓮縣"
    assert "earthquake" in out["hazards"]
    assert {"building_damage", "trapped_person"} <= set(out["impacts"])
    empty = scenario_rules.parse_brief("需要協助")
    assert empty["county"] is None and empty["hazards"] == []
    assert empty["reporter_roles"]  # sensible default roles
