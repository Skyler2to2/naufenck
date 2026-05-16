from __future__ import annotations

import re
from typing import Any


CHANNEL_SNAPSHOTS: dict[str, dict[str, Any]] = {
    "dim_cook_guide": {
        "channel_id": "UCXnWjmQ8BDE0sDIeZLK5yJg",
        "channel_name": "點 Cook Guide",
        "url": "https://www.youtube.com/@dim_cook_guide",
        "subscribers": 1230000,
        "video_count": 1600,
        "view_count": 2552000,
        "source": "cached_snapshot",
        "recent_videos": [
            {
                "id": "v8aq-YZ6bPw",
                "title": "【放題價$3xx】五星級酒店⭐️廚藝考試級菜式實拍！｜自選點心+老火湯+小菜＋甜品🍸午市套餐｜",
                "views": 52675,
                "likes": 1581,
                "comments": 95,
                "published": "2026-05-03",
            },
            {
                "id": "L8TCWwAHorc",
                "title": "【失傳食譜】懷舊紙包骨🍖後生仔未食過？｜牛油紙＋油＝燒烤🔥",
                "views": 59000,
                "likes": 1770,
                "comments": 106,
                "published": "2026-04-23",
            },
            {
                "id": "_T-0aoJP-Cw",
                "title": "[A Century-Old Teahouse] A Nostalgic Revival of Tea Drinking! 🫖｜24-Hour Lin Heung Tea House + Mon...",
                "views": 152000,
                "likes": 4560,
                "comments": 274,
                "published": "2026-04-23",
            },
            {
                "id": "P_UsAXgqEa8",
                "title": "[Real Story] Gold Selling Test: Final Price $1xxxx | Gold Shop vs. Gold Buyer | Investor Gatherin...",
                "views": 94000,
                "likes": 2820,
                "comments": 169,
                "published": "2026-04-14",
            },
            {
                "id": "IYnH0yhjZBI",
                "title": "【手工潮汕菜】實拍手拆滷水鵝頸🪿｜無骨九肚魚蠔餅🦪｜鐵板魚卜魚扣㊙️10條魚炒1碟？｜",
                "views": 109000,
                "likes": 3270,
                "comments": 196,
                "published": "2026-04-14",
            },
            {
                "id": "7kNjo3fMcPU",
                "title": "[Too Much Cheese 🧀] Korean Pork Chop 🐷 Specialty Store 🥓 This side dish is unforgettable! | Korea...",
                "views": 92000,
                "likes": 2760,
                "comments": 166,
                "published": "2026-04-14",
            },
        ],
    }
}


def _extract_snapshot_key(identifier: str) -> str:
    ident = identifier.strip().lower()
    match = re.search(r"/@([\w.-]+)", ident)
    if match:
        return match.group(1)
    if ident.startswith("@"):
        return ident[1:]
    if ident.startswith("http"):
        return ident.rstrip("/").split("/")[-1].removeprefix("@")
    return ident


def get_snapshot_channel(identifier: str) -> dict[str, Any] | None:
    key = _extract_snapshot_key(identifier)
    snapshot = CHANNEL_SNAPSHOTS.get(key)
    if not snapshot:
        return None
    return {
        **snapshot,
        "recent_videos": [video.copy() for video in snapshot.get("recent_videos", [])],
    }
