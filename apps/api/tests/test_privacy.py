from __future__ import annotations

from app.services.privacy_service import mask_address, public_coords, redact_text, reporter_key


def test_mask_address_strips_house_numbers_and_lanes():
    assert mask_address("南投縣埔里鎮南門里中山路二段 120 號") == "南投縣埔里鎮南門里中山路二段一帶"
    assert mask_address("南投縣仁愛鄉台14甲線 18K 旁 12 號 3 樓") == "南投縣仁愛鄉台14甲線 18K 旁一帶"
    assert mask_address("中正路12巷3弄5號") == "中正路一帶"
    assert mask_address("南投縣信義鄉東埔村") == "南投縣信義鄉東埔村"
    assert mask_address("") is None
    assert mask_address(None) is None


def test_public_coords_are_coarsened():
    assert public_coords(24.023512, 121.157289) == (24.024, 121.157)
    assert public_coords(None, None) == (None, None)


def test_redact_text_removes_contacts():
    out = redact_text("請打 0912-345-678 或 mail a.b@example.com 給我，身分證 A123456789，我是王小明")
    assert "0912" not in out and "example.com" not in out and "A123456789" not in out
    assert "王小明" not in out
    assert redact_text(None) is None
    assert redact_text("路基掏空，單線通行") == "路基掏空，單線通行"


def test_reporter_key_is_stable_and_prefers_contact():
    a = reporter_key("0912000101", "device-1")
    b = reporter_key("0912000101", "device-2")
    c = reporter_key(None, "device-1")
    assert a == b  # same person, two devices
    assert a != c
    assert reporter_key(None, None) is None
    assert reporter_key("  ", "") is None
    assert len(a) == 32 and "0912" not in a
