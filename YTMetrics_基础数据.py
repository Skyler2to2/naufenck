from __future__ import annotations
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import streamlit as st

from ytmetrics_youtube_client import YouTubeAPIError, YouTubeDataAPIClient
from ytmetrics_channel_snapshots import get_snapshot_channel
from ytmetrics_youtube_fallback import fetch_channel_via_browser

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# 有趣且时尚的新配色方案
COLOR_PALETTE = {
    "neon_pink": "#FF006E",
    "electric_blue": "#3A86FF",
    "vibrant_orange": "#FB5607",
    "lime_green": "#8AC926",
    "deep_purple": "#6A040F",
    "soft_mint": "#90BE6D",
    "lavender": "#CDB4DB",
    "cream_white": "#FFFCF9",
    "dark_charcoal": "#2B2D42",
    "hot_magenta": "#E63946",
    "sunshine_yellow": "#FFBE0B",
    "turquoise": "#06D6A0",
    # 保留一些旧键名以保持兼容性
    "bright_yellow": "#FFBE0B",
    "bright_pink": "#FF006E",
    "bright_green": "#8AC926",
    "black": "#2B2D42",
    "gray": "#A0A0A0",
    "deep_blue": "#3A86FF",
    "light_gray": "#FFFCF9",
    "orange": "#FB5607",
    "purple": "#6A040F",
}

if __name__ == "__main__":
    st.set_page_config(
        page_title="YTMetrics - HK Food YouTuber Analysis",
        page_icon="📊",
        layout="wide",
    )
    
    # 全局CSS样式 - 应用新配色方案
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-color: {COLOR_PALETTE['light_gray']};
        }}
        div[data-testid="stBlockContainer"] {{
            background-color: {COLOR_PALETTE['light_gray']};
        }}
        
        /* 按钮样式 */
        button[kind="primary"] {{
            background-color: {COLOR_PALETTE['deep_blue']} !important;
            color: white !important;
            border: none !important;
        }}
        button[kind="primary"]:hover {{
            background-color: {COLOR_PALETTE['bright_pink']} !important;
        }}
        
        /* 普通按钮 */
        button[kind="secondary"] {{
            border-color: {COLOR_PALETTE['deep_blue']} !important;
            color: {COLOR_PALETTE['deep_blue']} !important;
        }}
        button[kind="secondary"]:hover {{
            background-color: {COLOR_PALETTE['bright_yellow']} !important;
            border-color: {COLOR_PALETTE['bright_yellow']} !important;
            color: {COLOR_PALETTE['deep_blue']} !important;
        }}
        
        /* 滑块轨道颜色 */
        div[data-testid="stSliderThumbValue"] {{
            background-color: {COLOR_PALETTE['deep_blue']} !important;
            color: white !important;
        }}
        
        /* 滑块轨道 */
        div[role="slider"] {{
            background-color: {COLOR_PALETTE['deep_blue']} !important;
        }}
        
        /* 滑块轨道背景 */
        div.stSlider > div > div > div {{
            background-color: {COLOR_PALETTE['bright_yellow']} !important;
        }}
        
        /* 侧边栏 */
        section[data-testid="stSidebar"] {{
            background-color: {COLOR_PALETTE['light_gray']} !important;
        }}
        
        /* 输入框边框 */
        input[type="text"] {{
            border-color: {COLOR_PALETTE['deep_blue']} !important;
        }}
        
        /* 下拉菜单 */
        div[data-testid="stSelectbox"] > div {{
            border-color: {COLOR_PALETTE['deep_blue']} !important;
        }}
        
        /* 标题颜色 */
        h1, h2, h3 {{
            color: {COLOR_PALETTE['deep_blue']} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

# ---------------------------------------------------------------------------
# 香港美食类型关键词（中英 / 繁简混合）
# ---------------------------------------------------------------------------
HK_FOOD_TYPES = {
    "茶餐廳 / Cha Chaan Teng": ["茶餐廳", "茶餐厅", "cha chaan teng", "港式", "蛋撻", "菠蘿包", "奶茶"],
    "點心 / Dim Sum": ["點心", "点心", "dim sum", "蝦餃", "燒賣", "腸粉", "yum cha"],
    "燒臘 / BBQ": ["燒臘", "烧腊", "燒鵝", "叉燒", "char siu", "roast goose", "siu mei"],
    "火鍋 / Hot Pot": ["火鍋", "火锅", "hot pot", "打邊爐", "hotpot"],
    "海鮮 / Seafood": ["海鮮", "海鲜", "seafood", "lobster", "螃蟹", "蝦", "魚生"],
    "甜品 / Dessert": ["甜品", "甜點", "dessert", "糖水", "雪糕", "蛋糕", "cake", "ice cream"],
    "麵食 / Noodles": ["雲吞麵", "車仔麵", "noodle", "ramen", "拉麵", "牛腩麵"],
    "街頭小食 / Street Food": ["街頭", "街头", "street food", "魚蛋", "雞蛋仔", "格仔餅", "煎釀三寶"],
    "日式 / Japanese": ["日式", "japanese", "壽司", "sushi", "刺身", "和牛", "omakase"],
    "西餐 / Western": ["西餐", "western", "意大利", "pasta", "pizza", "steak", "牛排", "burger"],
    "中菜 / Chinese": ["中菜", "粵菜", "粤菜", "chinese cuisine", "私房菜"],
    "韓式 / Korean": ["韓式", "韩式", "korean", "韓國", "kimchi", "烤肉"],
    "東南亞 / SE Asian": ["泰式", "thai", "越南", "vietnamese", "印尼", "馬來", "pho"],
    "咖啡店 / Cafe": ["咖啡", "cafe", "coffee", "latte", "brunch"],
    "飲品 / Drinks": ["飲品", "饮品", "bubble tea", "boba", "珍珠奶茶"],
}

# ---------------------------------------------------------------------------
# Mock 数据 — API key 缺失或调用失败时回退使用
# ---------------------------------------------------------------------------
# 默认示例：真实的香港美食/生活 YouTuber（由 YouTube API 搜索筛选）
EXAMPLE_CHANNELS = """@dim_cook_guide
@stephen_leung
@alfredchan
@taylor_r
@superchefjoe
@mm.millmilk
"""

MOCK_DATA = [
    {
        "channel_id": "UC_mock_giant",
        "channel_name": "巨人食量 (Sample)",
        "url": "https://www.youtube.com/@sample_giant",
        "subscribers": 320_000,
        "video_count": 412,
        "view_count": 58_200_000,
        "recent_videos": [
            {"title": "中環茶餐廳$50超抵食", "likes": 8200, "comments": 412, "published": "2026-05-05"},
            {"title": "深水埗街頭小食地圖：魚蛋雞蛋仔大比拼", "likes": 12300, "comments": 651, "published": "2026-04-28"},
            {"title": "日式拉麵 VS 港式雲吞麵", "likes": 9100, "comments": 380, "published": "2026-04-15"},
            {"title": "尖沙咀燒臘大公開", "likes": 7600, "comments": 290, "published": "2026-04-02"},
        ],
    },
    {
        "channel_id": "UC_mock_tiffany",
        "channel_name": "Tiffany 進食中 (Sample)",
        "url": "https://www.youtube.com/@sample_tiffany",
        "subscribers": 185_000,
        "video_count": 298,
        "view_count": 22_400_000,
        "recent_videos": [
            {"title": "旺角點心放題試食", "likes": 5400, "comments": 230, "published": "2026-05-08"},
            {"title": "銅鑼灣甜品店推介：糖水雪糕大集合", "likes": 7200, "comments": 410, "published": "2026-04-20"},
            {"title": "韓式烤肉 vs 港式燒臘", "likes": 6800, "comments": 295, "published": "2026-04-02"},
        ],
    },
    {
        "channel_id": "UC_mock_hungryhk",
        "channel_name": "Hungry Hong Kong (Sample)",
        "url": "https://www.youtube.com/@sample_hungryhk",
        "subscribers": 78_000,
        "video_count": 156,
        "view_count": 9_800_000,
        "recent_videos": [
            {"title": "HK Hot Pot Tour with Friends", "likes": 3200, "comments": 145, "published": "2026-05-01"},
            {"title": "Best Dim Sum in Central", "likes": 4100, "comments": 220, "published": "2026-04-18"},
            {"title": "Street Food Battle: Mongkok", "likes": 5600, "comments": 380, "published": "2026-03-28"},
        ],
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_channel_input(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def extract_food_types(titles: list[str]) -> list[str]:
    text = " ".join(titles).lower()
    detected = []
    for category, keywords in HK_FOOD_TYPES.items():
        if any(kw.lower() in text for kw in keywords):
            detected.append(category)
    return detected


def aggregate_recent_engagement(videos: list[dict], days: int) -> dict:
    """近 N 天点赞 + 评论汇总；若窗口内无视频，回退到点赞数最高的单条视频。"""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    recent = []
    for v in videos:
        try:
            pub = datetime.strptime(v["published"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        if pub >= cutoff:
            recent.append(v)

    if recent:
        return {
            "likes": sum(v.get("likes", 0) for v in recent),
            "comments": sum(v.get("comments", 0) for v in recent),
            "video_count": len(recent),
            "source": "recent",
            "top_title": "",
        }

    if videos:
        top = max(videos, key=lambda v: v.get("likes", 0))
        return {
            "likes": top.get("likes", 0),
            "comments": top.get("comments", 0),
            "video_count": 1,
            "source": "top",
            "top_title": top.get("title", ""),
        }

    return {"likes": 0, "comments": 0, "video_count": 0, "source": "empty", "top_title": ""}


def _safe_int(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def prepare_time_data(videos: list[dict]) -> pd.DataFrame:
    """将视频列表转换为可用于时间维度分析的 DataFrame。"""
    rows: list[dict] = []
    for video in videos or []:
        published_raw = str(video.get("published", "")).strip()
        published_at = pd.to_datetime(published_raw, errors="coerce")
        if pd.isna(published_at):
            continue

        likes = _safe_int(video.get("likes", 0))
        comments = _safe_int(video.get("comments", 0))
        views = _safe_int(video.get("views", 0))

        rows.append(
            {
                "id": str(video.get("id", "")),
                "title": str(video.get("title", "")),
                "published": published_at.date().isoformat(),
                "published_date": published_at.normalize(),
                "views": views,
                "likes": likes,
                "comments": comments,
                "engagement": likes + comments,
                "channel": str(video.get("channel", "")),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "id",
                "title",
                "published",
                "published_date",
                "views",
                "likes",
                "comments",
                "engagement",
                "channel",
            ]
        )

    df = pd.DataFrame(rows).sort_values("published_date").reset_index(drop=True)
    df["day_of_week"] = df["published_date"].dt.dayofweek
    df["day_name"] = df["published_date"].dt.day_name()
    df["month"] = df["published_date"].dt.month
    df["year_month"] = df["published_date"].dt.strftime("%Y-%m")
    df["week_of_year"] = df["published_date"].dt.isocalendar().week.astype(int)
    return df


def _build_daily_series(window_df: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp) -> list[dict]:
    date_index = pd.date_range(start_date, end_date, freq="D")

    if window_df.empty:
        grouped = pd.DataFrame(
            0,
            index=date_index,
            columns=["views", "likes", "comments", "engagement", "videos"],
        )
    else:
        grouped = (
            window_df.groupby("published_date")
            .agg(
                views=("views", "sum"),
                likes=("likes", "sum"),
                comments=("comments", "sum"),
                engagement=("engagement", "sum"),
                videos=("id", "count"),
            )
            .reindex(date_index, fill_value=0)
        )

    return [
        {
            "date": index.date().isoformat(),
            "views": int(row["views"]),
            "likes": int(row["likes"]),
            "comments": int(row["comments"]),
            "engagement": int(row["engagement"]),
            "videos": int(row["videos"]),
        }
        for index, row in grouped.iterrows()
    ]


def _calculate_change_pct(current_value: int, previous_value: int) -> float:
    if previous_value <= 0:
        return 100.0 if current_value > 0 else 0.0
    return round((current_value - previous_value) / previous_value * 100, 1)


def _describe_trend_direction(
    *,
    video_count: int,
    recent_7d_engagement: int,
    previous_7d_engagement: int,
    recent_7d_videos: int,
) -> str:
    if video_count <= 0:
        return "近 30 天没有检测到新视频发布"
    if previous_7d_engagement <= 0 and recent_7d_engagement > 0:
        return "近 7 天开始恢复更新，互动从低位回升"
    if recent_7d_engagement <= 0 and previous_7d_engagement > 0:
        return "最近 7 天没有新增互动，更新节奏明显放缓"

    change_pct = _calculate_change_pct(recent_7d_engagement, previous_7d_engagement)
    if change_pct >= 20:
        return f"近 7 天互动较前 7 天上升 {change_pct:.1f}%"
    if change_pct <= -20:
        return f"近 7 天互动较前 7 天下滑 {abs(change_pct):.1f}%"
    if recent_7d_videos <= 1:
        return "近 30 天更新频次较低，趋势判断以少量新视频表现为主"
    return "近 30 天互动整体保持平稳"


def build_growth_data(channel_data: dict, window_days: int = 30) -> dict:
    """将第 3 部分的时间维度分析标准化为 AI 输入层可消费的 growth_data。"""
    recent_videos = channel_data.get("recent_videos", [])
    source = str(channel_data.get("source", "youtube_api")).strip() or "youtube_api"

    all_video_df = prepare_time_data(recent_videos)
    end_date = pd.Timestamp(datetime.now(timezone.utc).date())
    start_date = end_date - pd.Timedelta(days=max(window_days - 1, 0))

    if all_video_df.empty:
        window_df = all_video_df.copy()
    else:
        window_df = all_video_df[
            (all_video_df["published_date"] >= start_date)
            & (all_video_df["published_date"] <= end_date)
        ].copy()

    series = _build_daily_series(window_df, start_date, end_date)
    series_df = pd.DataFrame(series)
    if not series_df.empty:
        series_df["rolling_7d_engagement"] = (
            series_df["engagement"].rolling(window=7, min_periods=1).sum().astype(int)
        )
        series_df["rolling_7d_views"] = (
            series_df["views"].rolling(window=7, min_periods=1).sum().astype(int)
        )
        series = series_df.to_dict(orient="records")
    upload_day_series = [point for point in series if int(point.get("videos", 0) or 0) > 0]

    recent_7d_engagement = int(series_df.tail(7)["engagement"].sum()) if not series_df.empty else 0
    previous_7d_engagement = (
        int(series_df.iloc[-14:-7]["engagement"].sum()) if len(series_df) >= 14 else 0
    )
    recent_7d_videos = int(series_df.tail(7)["videos"].sum()) if not series_df.empty else 0
    previous_7d_videos = int(series_df.iloc[-14:-7]["videos"].sum()) if len(series_df) >= 14 else 0

    total_views = int(window_df["views"].sum()) if not window_df.empty else 0
    total_engagement = int(window_df["engagement"].sum()) if not window_df.empty else 0
    video_count = int(len(window_df))
    active_days = int((series_df["videos"] > 0).sum()) if not series_df.empty else 0
    avg_views_per_video = round(total_views / video_count, 1) if video_count else 0.0
    avg_engagement_per_video = round(total_engagement / video_count, 1) if video_count else 0.0

    peak_day = (
        series_df.sort_values(["engagement", "views"], ascending=False).iloc[0].to_dict()
        if not series_df.empty
        else {"date": "", "engagement": 0, "views": 0, "videos": 0}
    )
    top_video = (
        window_df.sort_values(["engagement", "views"], ascending=False).iloc[0].to_dict()
        if not window_df.empty
        else {}
    )
    latest_video_date = (
        window_df["published_date"].max().date().isoformat() if not window_df.empty else ""
    )

    trend_direction = _describe_trend_direction(
        video_count=video_count,
        recent_7d_engagement=recent_7d_engagement,
        previous_7d_engagement=previous_7d_engagement,
        recent_7d_videos=recent_7d_videos,
    )

    if video_count <= 0:
        notable_change = "近 30 天没有检测到新视频，当前趋势图展示的是实际零发布、零互动状态。"
    else:
        notable_change = (
            f"近 {window_days} 天共发布 {video_count} 条视频，活跃 {active_days} 天，"
            f"单条平均互动 {avg_engagement_per_video:,.1f}；峰值出现在 {peak_day.get('date', '')}，"
            f"单日互动 {int(peak_day.get('engagement', 0)):,}。"
        )
        if top_video.get("title"):
            notable_change += f" 期间表现最强的视频是《{top_video['title']}》。"

    summary = {
        "window_days": window_days,
        "video_count": video_count,
        "active_days": active_days,
        "total_views": total_views,
        "total_engagement": total_engagement,
        "avg_views_per_video": avg_views_per_video,
        "avg_engagement_per_video": avg_engagement_per_video,
        "recent_7d_engagement": recent_7d_engagement,
        "previous_7d_engagement": previous_7d_engagement,
        "recent_7d_videos": recent_7d_videos,
        "previous_7d_videos": previous_7d_videos,
        "engagement_change_pct": _calculate_change_pct(recent_7d_engagement, previous_7d_engagement),
        "trend_direction": trend_direction,
        "notable_change": notable_change,
        "latest_video_date": latest_video_date,
        "peak_date": str(peak_day.get("date", "")),
        "peak_engagement": int(peak_day.get("engagement", 0)),
        "peak_views": int(peak_day.get("views", 0)),
        "top_video_title": str(top_video.get("title", "")),
    }

    raw_excerpt = json.dumps(
        {
            "summary": summary,
            "series_tail": series[-7:],
            "source_channel": channel_data.get("channel_name", ""),
        },
        ensure_ascii=False,
    )[:1600]

    return {
        "summary": summary,
        "series": series,
        "upload_day_series": upload_day_series,
        "comparison": {
            "recent_7d_engagement": recent_7d_engagement,
            "previous_7d_engagement": previous_7d_engagement,
            "recent_7d_videos": recent_7d_videos,
            "previous_7d_videos": previous_7d_videos,
            "engagement_change_pct": summary["engagement_change_pct"],
        },
        "data_source": f"{source}_time_series",
        "raw_excerpt": raw_excerpt,
    }


# ---------------------------------------------------------------------------
# YouTube API
# ---------------------------------------------------------------------------

def _extract_youtube_target(ident: str) -> dict:
    raw = ident.strip()
    target = {
        "kind": "unknown",
        "raw": raw,
        "video_id": None,
        "channel_id": None,
        "handle": None,
        "playlist_id": None,
    }
    if not raw:
        return target

    if raw.startswith("UC") and len(raw) >= 22 and "/" not in raw:
        target["kind"] = "channel_id"
        target["channel_id"] = raw
        return target

    if raw.startswith("@"):
        target["kind"] = "handle"
        target["handle"] = raw[1:]
        return target

    if not raw.startswith("http"):
        target["kind"] = "handle"
        target["handle"] = raw
        return target

    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    query = parse_qs(parsed.query or "")

    if "list" in query:
        playlist_id = (query.get("list") or [""])[0].strip()
        if playlist_id:
            target["kind"] = "playlist"
            target["playlist_id"] = playlist_id
            return target

    if "v" in query:
        video_id = (query.get("v") or [""])[0].strip()
        if video_id:
            target["kind"] = "video"
            target["video_id"] = video_id
            return target

    short_match = re.search(r"/(?:shorts|live|embed|v)/([0-9A-Za-z_-]{11})", path)
    if short_match:
        target["kind"] = "video"
        target["video_id"] = short_match.group(1)
        return target

    if "youtu.be" in host:
        slug = path.strip("/").split("/")[0]
        if re.fullmatch(r"[0-9A-Za-z_-]{11}", slug or ""):
            target["kind"] = "video"
            target["video_id"] = slug
            return target

    channel_match = re.search(r"/channel/(UC[\w-]+)", path)
    if channel_match:
        target["kind"] = "channel_id"
        target["channel_id"] = channel_match.group(1)
        return target

    handle_match = re.search(r"/@([\w.-]+)", path)
    if handle_match:
        target["kind"] = "handle"
        target["handle"] = handle_match.group(1)
        return target

    custom_match = re.search(r"/(?:user|c)/([\w.-]+)", path)
    if custom_match:
        target["kind"] = "handle"
        target["handle"] = custom_match.group(1)
        return target

    return target


def _resolve_channel_id(youtube, ident: str) -> str | None:
    target = _extract_youtube_target(ident)
    if target["kind"] == "channel_id":
        return target["channel_id"]
    if target["kind"] == "playlist":
        return None
    if target["kind"] == "video" and target["video_id"]:
        try:
            resp = youtube.videos().list(part="snippet", id=target["video_id"]).execute()
            items = resp.get("items", [])
            if items:
                channel_id = items[0].get("snippet", {}).get("channelId")
                if channel_id:
                    return channel_id
        except YouTubeAPIError as exc:
            st.error(f"视频链接反查频道失败 ({target['video_id']}): {exc}")
        return None

    handle = None
    if target["kind"] == "handle":
        handle = target["handle"]

    if not handle:
        if target["kind"] == "unknown":
            st.error(f"无法识别该 YouTube 链接或标识: {ident}")
        return None

    try:
        resp = youtube.channels().list(part="id", forHandle=handle).execute()
        items = resp.get("items", [])
        if items:
            return items[0]["id"]

        resp = youtube.search().list(part="snippet", q=handle, type="channel", maxResults=3).execute()
        items = resp.get("items", [])
        if items:
            return items[0]["snippet"]["channelId"]
    except YouTubeAPIError as exc:
        st.error(f"API 调用异常 ({handle}): {exc}")

    return None


def fetch_youtube_data(identifiers: list[str], api_key: str) -> tuple[list[dict], list[str]]:
    """返回 (channel_data, errors)。失败时 errors 非空。"""
    errors: list[str] = []
    results: list[dict] = []

    try:
        youtube = YouTubeDataAPIClient(api_key)
    except Exception as exc:
        errors.append(f"无法初始化 YouTube API 客户端: {exc}")
        return [], errors

    channel_ids: list[str] = []
    fallback_idents: list[str] = []
    for ident in identifiers:
        target = _extract_youtube_target(ident)
        if target["kind"] == "playlist" and target["playlist_id"]:
            errors.append(f"暂不支持 playlist 作为主入口，请改用频道或视频链接: {ident}")
            continue
        cid = _resolve_channel_id(youtube, ident)
        if cid:
            channel_ids.append(cid)
        else:
            fallback_idents.append(ident)

    for chunk_start in range(0, len(channel_ids), 50):
        chunk = channel_ids[chunk_start : chunk_start + 50]
        try:
            ch_resp = youtube.channels().list(
                part="snippet,statistics,contentDetails",
                id=",".join(chunk),
            ).execute()
        except YouTubeAPIError as exc:
            errors.append(f"channels.list 调用失败: {exc}")
            continue

        for item in ch_resp.get("items", []):
            cid = item["id"]
            snippet = item["snippet"]
            stats = item.get("statistics", {})
            uploads_pl = item["contentDetails"]["relatedPlaylists"]["uploads"]

            recent_videos: list[dict] = []
            try:
                pl_resp = youtube.playlistItems().list(
                    part="contentDetails",
                    playlistId=uploads_pl,
                    maxResults=20,
                ).execute()
                video_ids = [pi["contentDetails"]["videoId"] for pi in pl_resp.get("items", [])]
                if video_ids:
                    v_resp = youtube.videos().list(
                        part="snippet,statistics",
                        id=",".join(video_ids),
                    ).execute()
                    for v in v_resp.get("items", []):
                        recent_videos.append({
                            "id": v["id"],
                            "title": v["snippet"]["title"],
                            "views": int(v["statistics"].get("viewCount", 0)),
                            "likes": int(v["statistics"].get("likeCount", 0)),
                            "comments": int(v["statistics"].get("commentCount", 0)),
                            "published": v["snippet"]["publishedAt"][:10],
                        })
            except YouTubeAPIError as exc:
                errors.append(f"获取 {snippet.get('title')} 视频失败: {exc}")

            results.append({
                "channel_id": cid,
                "channel_name": snippet["title"],
                "url": f"https://www.youtube.com/channel/{cid}",
                "subscribers": int(stats.get("subscriberCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
                "view_count": int(stats.get("viewCount", 0)),
                "recent_videos": recent_videos,
                "source": "youtube_api",
            })

    for ident in fallback_idents:
        try:
            results.append(fetch_channel_via_browser(ident))
            errors.append(f"官方 YouTube API 解析失败，已自动切换浏览器兜底模式: {ident}")
        except Exception as exc:
            snapshot = get_snapshot_channel(ident) if os.environ.get("YTMETRICS_ALLOW_SNAPSHOT_FALLBACK") == "true" else None
            if snapshot:
                results.append(snapshot)
                errors.append(f"实时抓取失败，已切换到本地缓存快照模式: {ident}")
            else:
                errors.append(f"无法解析: {ident} ({exc})")

    return results, errors


def load_data(identifiers: list[str]) -> tuple[list[dict], bool, list[str]]:
    """返回 (data, used_mock, errors)。"""
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return MOCK_DATA, True, ["未检测到 YOUTUBE_API_KEY，使用 mock 数据"]

    data, errors = fetch_youtube_data(identifiers, api_key)
    if not data:
        return MOCK_DATA, True, errors + ["API 未返回数据，回退到 mock"]
    return data, False, errors


if __name__ == "__main__":
    # -----------------------------------------------------------------------
    # Session state
    # -----------------------------------------------------------------------
    if "page" not in st.session_state:
        st.session_state.page = "home"
    if "data" not in st.session_state:
        st.session_state.data = None
    if "used_mock" not in st.session_state:
        st.session_state.used_mock = False
    if "errors" not in st.session_state:
        st.session_state.errors = []
    if "channel_text" not in st.session_state:
        st.session_state.channel_text = ""

    def load_example_channels():
        st.session_state.channel_text = EXAMPLE_CHANNELS

    def go_to_dashboard(data, used_mock, errors):
        st.session_state.data = data
        st.session_state.used_mock = used_mock
        st.session_state.errors = errors
        st.session_state.page = "dashboard"

    def go_to_home():
        st.session_state.page = "home"
        st.session_state.data = None
        st.session_state.errors = []

    # -----------------------------------------------------------------------
    # Pages
    # -----------------------------------------------------------------------
    if st.session_state.page == "home":
        st.title("📊 YTMetrics — HK Food YouTuber Analysis")
        st.subheader("Turn Hong Kong Food Channels into Actionable Insights")
        st.markdown("---")

        api_key_present = bool(os.environ.get("YOUTUBE_API_KEY", "").strip())
        if api_key_present:
            st.success("✅ 检测到 `YOUTUBE_API_KEY`，将调用 YouTube Data API 拉取实时数据")
        else:
            st.warning("⚠️ 未设置 `YOUTUBE_API_KEY`，将使用内置 mock 示例数据")

        tab1, tab2 = st.tabs(["📝 粘贴频道列表", "📂 上传 CSV"])

        with tab1:
            col_btn1, col_btn2 = st.columns([1, 3])
            with col_btn1:
                st.button(
                    "🍜 Load HK food example",
                    on_click=load_example_channels,
                    use_container_width=True,
                )
            with col_btn2:
                st.caption(
                    "示例：點 Cook Guide、Stephen Leung 吃喝玩樂、Alfred Chan、"
                    "Taylor R、Chef Joe HK、Mill MILK（均为真实 HK 美食/生活频道）"
                )

            text = st.text_area(
                "每行一个 Channel URL / @handle / Channel ID",
                height=200,
                placeholder=(
                    "https://www.youtube.com/@channel_handle\n"
                    "@another_handle\n"
                    "UCxxxxxxxxxxxxxxxxxxxxxx"
                ),
                key="channel_text",
            )
            if st.button("Analyze", use_container_width=True, key="btn_text"):
                ids = parse_channel_input(text)
                if not ids and api_key_present:
                    st.error("请至少输入一个频道")
                else:
                    with st.spinner("正在拉取频道数据..."):
                        data, used_mock, errors = load_data(ids)
                    go_to_dashboard(data, used_mock, errors)
                    st.rerun()

        with tab2:
            uploaded = st.file_uploader(
                "上传 CSV，包含 `channel` 列（URL / @handle / ID）",
                type=["csv"],
            )
            if uploaded is not None:
                try:
                    df_in = pd.read_csv(uploaded)
                    col = "channel" if "channel" in df_in.columns else df_in.columns[0]
                    ids = df_in[col].dropna().astype(str).tolist()
                    st.write(f"已加载 {len(ids)} 个频道，预览：")
                    st.dataframe(df_in.head(10), use_container_width=True)
                    if st.button("Analyze CSV", use_container_width=True, key="btn_csv"):
                        with st.spinner("正在拉取频道数据..."):
                            data, used_mock, errors = load_data(ids)
                        go_to_dashboard(data, used_mock, errors)
                        st.rerun()
                except Exception as e:
                    st.error(f"读取 CSV 失败: {e}")

    elif st.session_state.page == "dashboard":
        with st.sidebar:
            st.title("Navigation")
            if st.button("⬅️ Back to Search", use_container_width=True):
                go_to_home()
                st.rerun()
            st.markdown("---")
            st.markdown("Jump to:")
            st.markdown(
                """
                - [📊 Summary Table](#summary-metrics)
                - [🔍 Channel Details](#channel-details)
                """
            )

        st.title("HK Food YouTuber Dashboard")
        if st.session_state.used_mock:
            st.info("当前展示 **mock 示例数据**。设置环境变量 `YOUTUBE_API_KEY` 后重启即可拉取实时数据。")
        for msg in st.session_state.errors:
            st.warning(msg)
        st.markdown("---")

        data = st.session_state.data or []
        if not data:
            st.warning("没有可显示的数据")
        else:
            rows = []
            for ch in data:
                videos = ch.get("recent_videos", [])
                eng7 = aggregate_recent_engagement(videos, 7)
                eng30 = aggregate_recent_engagement(videos, 30)
                food_types = extract_food_types([v["title"] for v in videos])

                rows.append({
                    "Channel ID": ch["channel_id"],
                    "Channel": ch["channel_name"],
                    "Subscribers": ch["subscribers"],
                    "Videos": ch["video_count"],
                    "Total Views": ch["view_count"],
                    "7d 互动 (👍+💬)": eng7["likes"] + eng7["comments"],
                    "7d 来源": "近7天" if eng7["source"] == "recent" else "Top视频回退",
                    "30d 互动 (👍+💬)": eng30["likes"] + eng30["comments"],
                    "30d 来源": "近30天" if eng30["source"] == "recent" else "Top视频回退",
                    "Food Types": ", ".join(food_types) or "—",
                })

            df = pd.DataFrame(rows)

            st.subheader("📊 Summary Metrics", anchor="summary-metrics")
            st.dataframe(
                df,
                use_container_width=True,
                column_config={
                    "Subscribers": st.column_config.NumberColumn(format="%d"),
                    "Videos": st.column_config.NumberColumn(format="%d"),
                    "Total Views": st.column_config.NumberColumn(format="%d"),
                    "7d 互动 (👍+💬)": st.column_config.NumberColumn(format="%d"),
                    "30d 互动 (👍+💬)": st.column_config.NumberColumn(format="%d"),
                },
            )

            csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ Download CSV",
                data=csv_bytes,
                file_name="hk_food_youtubers.csv",
                mime="text/csv",
            )

            st.markdown("---")
            st.subheader("🔍 Channel Details", anchor="channel-details")
            for ch in data:
                videos = ch.get("recent_videos", [])
                eng7 = aggregate_recent_engagement(videos, 7)
                eng30 = aggregate_recent_engagement(videos, 30)
                food_types = extract_food_types([v["title"] for v in videos])

                with st.expander(f"📌 {ch['channel_name']}  ·  {ch['channel_id']}", expanded=False):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Subscribers", f"{ch['subscribers']:,}")
                    c2.metric("Total Videos", f"{ch['video_count']:,}")
                    c3.metric("Total Views", f"{ch['view_count']:,}")

                    c1, c2 = st.columns(2)
                    with c1:
                        if eng7["source"] == "recent":
                            st.markdown(f"**近 7 天互动量**（{eng7['video_count']} 条视频）")
                        elif eng7["source"] == "top":
                            st.markdown(f"**近 7 天无新视频，回退到点赞最高视频**")
                            st.caption(f"《{eng7['top_title']}》")
                        else:
                            st.markdown("**近 7 天**：无数据")
                        st.write(f"👍 {eng7['likes']:,}  ·  💬 {eng7['comments']:,}")

                    with c2:
                        if eng30["source"] == "recent":
                            st.markdown(f"**近 30 天互动量**（{eng30['video_count']} 条视频）")
                        elif eng30["source"] == "top":
                            st.markdown(f"**近 30 天无新视频，回退到点赞最高视频**")
                            st.caption(f"《{eng30['top_title']}》")
                        else:
                            st.markdown("**近 30 天**：无数据")
                        st.write(f"👍 {eng30['likes']:,}  ·  💬 {eng30['comments']:,}")

                    st.markdown(f"**🍜 涉及美食类型：** {', '.join(food_types) if food_types else '未识别'}")

                    if videos:
                        st.markdown("**最近视频：**")
                        vdf = pd.DataFrame(videos)[["published", "title", "likes", "comments"]]
                        vdf = vdf.rename(columns={
                            "published": "发布日期",
                            "title": "标题",
                            "likes": "👍",
                            "comments": "💬",
                        })
                        st.dataframe(vdf, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.caption("Powered by YTMetrics")
