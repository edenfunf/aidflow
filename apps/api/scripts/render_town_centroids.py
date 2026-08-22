import json, pathlib, sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
lines = ['''"""台灣 368 個鄉鎮市區的代表點（generated — do not edit by hand）。

來源：內政部消防署「避難收容處所點位檔」(data.gov.tw dataset 73242)。
每個鄉鎮市區取該轄內所有收容處所座標的**中位數**——中位數而非平均數，
單一筆打錯的座標就無法把代表點拉走。收容處所一定位於有人居住的陸地上，
所以這些點必然落在該鄉鎮的可居住區域內，比幾何形心更適合用來定位。

這不是權威的行政區形心，也不能當作地理編碼結果使用；它的用途是
「把一個點歸到最近的鄉鎮」以及「在該鄉鎮附近放一個點」。

重新產生：
    cd apps/api && python scripts/derive_town_centroids.py out.json
    python scripts/render_town_centroids.py out.json app/utils/town_centroids.py
"""
from __future__ import annotations

# {縣市: {鄉鎮市區: (lat, lon)}}
TOWN_CENTROIDS: dict[str, dict[str, tuple[float, float]]] = {''']
total = 0
for county in sorted(data):
    towns = data[county]
    lines.append(f'    "{county}": {{')
    for town in sorted(towns):
        lat, lon, n = towns[town]
        lines.append(f'        "{town}": ({lat}, {lon}),')
        total += 1
    lines.append("    },")
lines.append("}")
lines.append("")
pathlib.Path(sys.argv[2]).write_text("\n".join(lines), encoding="utf-8")
print("wrote", sys.argv[2], "townships:", total)
