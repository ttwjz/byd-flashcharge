"""Download province GeoJSON files from DataV GeoAtlas for map drill-down + PiP geocoding."""

import json
import os
import time
import requests

MAPS_DIR = os.path.join("public", "static", "maps")
BASE_URL = "https://geo.datav.aliyun.com/areas_v3/bound"

# adcode -> province name (ECharts china.js uses these names)
PROVINCES = {
    "100000": "全国",
    "110000": "北京",
    "120000": "天津",
    "130000": "河北",
    "140000": "山西",
    "150000": "内蒙古",
    "210000": "辽宁",
    "220000": "吉林",
    "230000": "黑龙江",
    "310000": "上海",
    "320000": "江苏",
    "330000": "浙江",
    "340000": "安徽",
    "350000": "福建",
    "360000": "江西",
    "370000": "山东",
    "410000": "河南",
    "420000": "湖北",
    "430000": "湖南",
    "440000": "广东",
    "450000": "广西",
    "460000": "海南",
    "500000": "重庆",
    "510000": "四川",
    "520000": "贵州",
    "530000": "云南",
    "540000": "西藏",
    "610000": "陕西",
    "620000": "甘肃",
    "630000": "青海",
    "640000": "宁夏",
    "650000": "新疆",
    "710000": "台湾",
    "810000": "香港",
    "820000": "澳门",
}

def download_all():
    os.makedirs(MAPS_DIR, exist_ok=True)

    # Also write the province name -> adcode mapping as JSON for frontend use
    name_to_adcode = {name: code for code, name in PROVINCES.items() if code != "100000"}

    for adcode, name in PROVINCES.items():
        filename = f"{adcode}_full.json"
        filepath = os.path.join(MAPS_DIR, filename)

        if os.path.exists(filepath):
            print(f"  Skip {name} ({adcode}) - already exists")
            continue

        url = f"{BASE_URL}/{filename}"
        print(f"  Downloading {name} ({adcode})...", end=" ", flush=True)

        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

            size_kb = os.path.getsize(filepath) / 1024
            print(f"OK ({size_kb:.0f} KB)")
        except Exception as e:
            print(f"FAILED: {e}")

        time.sleep(0.3)

    # Write mapping file
    mapping_path = os.path.join(MAPS_DIR, "province_map.json")
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(name_to_adcode, f, ensure_ascii=False, indent=2)
    print(f"\nProvince mapping written to {mapping_path}")
    print("Done!")


if __name__ == "__main__":
    download_all()
