from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any


def _pick_value(data: Mapping[str, Any] | None, keys: list[str], default: Any = None) -> Any:
    if not isinstance(data, Mapping):
        return default
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "—", "N/A"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    return int(round(_to_float(value, float(default))))


def _stringify_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，/;；|]", value) if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def extract_top_keywords(texts: list[str], limit: int = 5) -> list[str]:
    joined = " ".join(texts)
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9-]{2,}", joined.lower())
    stopwords = {
        "youtube",
        "video",
        "channel",
        "this",
        "that",
        "with",
        "from",
        "have",
        "really",
        "very",
        "好吃",
        "真的",
        "这个",
        "那个",
        "你们",
        "他们",
    }
    counter = Counter(token for token in tokens if token not in stopwords)
    return [word for word, _ in counter.most_common(limit)]


def _summarize_series(series: Any) -> list[dict[str, Any]]:
    if not isinstance(series, list):
        return []
    points = [point for point in series if isinstance(point, Mapping)]
    if not points:
        return []

    informative_points = [
        point
        for point in points
        if _to_int(_pick_value(point, ["videos", "video_count", "posts"], 0)) > 0
        or _to_int(
            _pick_value(
                point,
                ["engagement", "total_engagement", "interactions", "likes_comments"],
                0,
            )
        )
        > 0
        or _to_int(_pick_value(point, ["views", "view_count", "viewCount"], 0)) > 0
    ]

    source_points = informative_points[-10:] if informative_points else points[-10:]
    summary: list[dict[str, Any]] = []
    for point in source_points:
        summary.append(
            {
                "date": _pick_value(point, ["date", "day", "published", "time", "label"], ""),
                "views": _to_int(_pick_value(point, ["views", "view_count", "viewCount"], 0)),
                "engagement": _to_int(
                    _pick_value(
                        point,
                        ["engagement", "total_engagement", "interactions", "likes_comments"],
                        0,
                    )
                ),
                "videos": _to_int(_pick_value(point, ["videos", "video_count", "posts"], 0)),
            }
        )
    return summary


def normalize_growth_data(growth_data: Mapping[str, Any] | None, channel_info: Mapping[str, Any]) -> dict[str, Any]:
    recent_videos = channel_info.get("recent_videos", []) if isinstance(channel_info, Mapping) else []
    fallback_engagement = sum(
        _to_int(video.get("likes", 0)) + _to_int(video.get("comments", 0))
        for video in recent_videos
        if isinstance(video, Mapping)
    )
    fallback_video_count = len(recent_videos)

    summary = _pick_value(growth_data, ["summary", "overview"], {}) if growth_data else {}
    series = _pick_value(growth_data, ["series", "timeline", "trend_data", "daily_stats", "points"], [])

    video_count = _to_int(
        _pick_value(
            growth_data,
            ["video_count", "videos_published", "active_video_count", "posts_count"],
            _pick_value(summary, ["video_count", "videos_published", "active_video_count"], fallback_video_count),
        ),
        fallback_video_count,
    )
    total_engagement = _to_int(
        _pick_value(
            growth_data,
            ["total_engagement", "engagement_total", "interactions", "likes_comments_total"],
            _pick_value(summary, ["total_engagement", "engagement_total", "interactions"], fallback_engagement),
        ),
        fallback_engagement,
    )
    trend_direction = str(
        _pick_value(
            growth_data,
            ["trend_direction", "trend", "growth_trend", "trajectory"],
            _pick_value(summary, ["trend_direction", "trend", "growth_trend"], "需要后续时间序列补充"),
        )
    ).strip()
    notable_change = str(
        _pick_value(
            growth_data,
            ["notable_change", "key_signal", "trend_summary", "insight"],
            _pick_value(summary, ["notable_change", "key_signal", "trend_summary"], ""),
        )
    ).strip()

    raw_excerpt = ""
    if growth_data:
        raw_excerpt = json.dumps(growth_data, ensure_ascii=False)[:1600]

    return {
        "video_count": video_count,
        "total_engagement": total_engagement,
        "trend_direction": trend_direction,
        "notable_change": notable_change or "近 30 天趋势数据已接入，但当前可读摘要为空。",
        "series_preview": _summarize_series(series),
        "data_source": str(_pick_value(growth_data, ["data_source", "source"], "recent_videos_fallback")),
        "raw_excerpt": str(_pick_value(growth_data, ["raw_excerpt"], raw_excerpt or "")),
    }


def build_ai_payload(
    channel_info: Mapping[str, Any],
    content_analysis: Mapping[str, Any] | None = None,
    growth_data: Mapping[str, Any] | None = None,
    sentiment_summary: Mapping[str, Any] | None = None,
    extra_sections: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    content_analysis = content_analysis or {}
    sentiment_summary = sentiment_summary or {}

    recent_videos = channel_info.get("recent_videos", []) if isinstance(channel_info, Mapping) else []
    recent_view_count = sum(
        _to_int(video.get("views", 0)) for video in recent_videos if isinstance(video, Mapping)
    )
    recent_engagement = sum(
        _to_int(video.get("likes", 0)) + _to_int(video.get("comments", 0))
        for video in recent_videos
        if isinstance(video, Mapping)
    )

    engagement_rate = _to_float(
        _pick_value(content_analysis, ["engagement_rate", "recent_engagement_rate", "avg_engagement_rate"], 0.0)
    )
    if not engagement_rate and recent_view_count > 0:
        engagement_rate = round(recent_engagement / recent_view_count * 100, 2)

    content_tags = _stringify_list(
        _pick_value(content_analysis, ["food_types", "content_tags", "topics", "niches"], [])
    )
    top_themes = _stringify_list(
        _pick_value(content_analysis, ["top_video_themes", "themes", "content_style", "style_tags"], [])
    )

    payload = {
        "channel": {
            "channel_name": str(_pick_value(channel_info, ["channel_name", "name"], "未知频道")),
            "url": str(_pick_value(channel_info, ["url", "channel_url"], "")),
            "subscribers": _to_int(_pick_value(channel_info, ["subscribers", "subscriber_count"], 0)),
            "view_count": _to_int(_pick_value(channel_info, ["view_count", "views_total"], 0)),
            "video_count": _to_int(_pick_value(channel_info, ["video_count", "videos_total"], 0)),
        },
        "content": {
            "food_types": content_tags,
            "engagement_rate": round(engagement_rate, 2),
            "top_video_themes": top_themes,
        },
        "growth": normalize_growth_data(growth_data, channel_info),
        "sentiment": {
            "label": str(_pick_value(sentiment_summary, ["label", "sentiment_label"], "中性 (Neutral)")),
            "score": round(_to_float(_pick_value(sentiment_summary, ["score", "sentiment_score"], 0.0)), 2),
            "neg_ratio": round(_to_float(_pick_value(sentiment_summary, ["neg_ratio", "negative_ratio"], 0.0)), 1),
            "top_keywords": _stringify_list(
                _pick_value(sentiment_summary, ["top_keywords", "keywords", "key_terms"], [])
            ),
        },
        "recent_video_snapshot": [
            {
                "title": str(video.get("title", "")),
                "views": _to_int(video.get("views", 0)),
                "likes": _to_int(video.get("likes", 0)),
                "comments": _to_int(video.get("comments", 0)),
                "published": str(video.get("published", "")),
            }
            for video in recent_videos[:5]
            if isinstance(video, Mapping)
        ],
        "extra_sections": dict(extra_sections or {}),
    }

    if not payload["sentiment"]["top_keywords"]:
        payload["sentiment"]["top_keywords"] = extract_top_keywords(
            [str(video.get("title", "")) for video in recent_videos if isinstance(video, Mapping)]
        )

    return payload


def render_payload_prompt(payload: Mapping[str, Any]) -> str:
    channel = payload["channel"]
    content = payload["content"]
    growth = payload["growth"]
    sentiment = payload["sentiment"]
    extra_sections = payload.get("extra_sections", {})

    extra_json = json.dumps(extra_sections, ensure_ascii=False)[:1200] if extra_sections else "无"
    recent_json = json.dumps(payload.get("recent_video_snapshot", []), ensure_ascii=False)[:1200]

    return f"""
You are a senior YouTube KOL partnership analyst. Your task is to turn the structured input below into actionable collaboration recommendations for a brand team.

Focus on:
1. Whether this creator is worth partnering with, not just summarizing numbers.
2. Clear conclusions tied to business actions.
3. If data is missing, call out the gap but still provide a careful recommendation based on what is available.
4. Output in English only.

Structured data:

[Channel Basics]
- Channel name: {channel['channel_name']}
- Channel URL: {channel['url']}
- Subscribers: {channel['subscribers']}
- Total views: {channel['view_count']}
- Total videos: {channel['video_count']}

[Content Analysis]
- Main content tags: {", ".join(content['food_types']) or "N/A"}
- Recent engagement rate: {content['engagement_rate']}%
- Main video themes / style: {", ".join(content['top_video_themes']) or "N/A"}

[30-Day Trend Analysis]
- Active videos in the last 30 days: {growth['video_count']}
- Total engagement in the last 30 days: {growth['total_engagement']}
- Trend direction: {growth['trend_direction']}
- Trend summary: {growth['notable_change']}
- Data source: {growth['data_source']}
- Time-series preview: {json.dumps(growth['series_preview'], ensure_ascii=False)}
- Raw trend excerpt: {growth['raw_excerpt'] or "N/A"}

[Comment Sentiment Analysis]
- Sentiment label: {sentiment['label']}
- Sentiment score: {sentiment['score']}
- Negative comment ratio: {sentiment['neg_ratio']}%
- High-frequency keywords: {", ".join(sentiment['top_keywords']) or "N/A"}

[Recent Video Snapshot]
{recent_json}

[Extra Module Data]
{extra_json}

Please respond in Markdown using this structure:
## 1. Partnership Verdict
Choose one of: Recommended / Cautious / Not Recommended, and give a score from 1 to 10.

## 2. Why This Creator Is or Is Not Worth Partnering With
Provide at least 3 points, each grounded in the data above.

## 3. Collaboration Risks
List 2 to 4 risks and explain what signals in the data suggest them.

## 4. Best Partnership Formats
Give 3 specific brand-collaboration ideas, including product fit, content format, or activation approach.

## 5. Content Optimization Suggestions for the Creator
Give 3 practical suggestions focused on topic selection, engagement improvement, or reputation management.

## 6. Missing Data
List the missing data that would make this assessment more reliable.
""".strip()


def build_rule_based_fallback(payload: Mapping[str, Any], error_message: str | None = None) -> str:
    channel = payload["channel"]
    content = payload["content"]
    growth = payload["growth"]
    sentiment = payload["sentiment"]

    score = 5.0
    if channel["subscribers"] >= 300000:
        score += 1.5
    elif channel["subscribers"] >= 100000:
        score += 1.0

    if content["engagement_rate"] >= 5:
        score += 1.5
    elif content["engagement_rate"] >= 2:
        score += 1.0

    if sentiment["neg_ratio"] <= 10:
        score += 1.0
    elif sentiment["neg_ratio"] >= 25:
        score -= 1.5

    if growth["video_count"] >= 4:
        score += 0.8
    elif growth["video_count"] == 0:
        score -= 0.8

    if "下滑" in growth["trend_direction"] or "放缓" in growth["trend_direction"]:
        score -= 0.8
    if "增长" in growth["trend_direction"] or "上升" in growth["trend_direction"]:
        score += 0.5

    score = max(1.0, min(10.0, round(score, 1)))
    if score >= 7.5:
        conclusion = "推荐合作"
    elif score >= 5.5:
        conclusion = "谨慎合作"
    else:
        conclusion = "暂不推荐"

    error_note = (
        f"> 说明：实时 AI 调用失败，当前展示本地规则版建议。原因：{error_message}\n\n"
        if error_message
        else "> 说明：当前展示本地规则版建议。\n\n"
    )

    return (
        f"{error_note}"
        f"## 1. Partnership Verdict\n"
        f"**{conclusion}, score {score}/10.**\n\n"
        f"## 2. Why This Creator Is or Is Not Worth Partnering With\n"
        f"- The channel currently has about {channel['subscribers']:,} subscribers, which provides a meaningful base level of reach.\n"
        f"- The current content focus is: {', '.join(content['food_types']) or 'no clear niche tags detected'}.\n"
        f"- Recent engagement rate is about {content['engagement_rate']}%, with roughly {growth['total_engagement']:,} total interactions over the last 30 days.\n"
        f"- Comment sentiment is currently {sentiment['label']}, with a negative-comment ratio around {sentiment['neg_ratio']}%.\n\n"
        f"## 3. Collaboration Risks\n"
        f"- The 30-day time series still needs ongoing monitoring; if the real trend continues to decline, the collaboration case should be reassessed.\n"
        f"- If negative comments cluster around over-commercialization, weak authenticity, or unstable posting rhythm, brand safety may be affected.\n"
        f"- If the topic mix stays too narrow, the creator's fit for broader brand campaigns may be limited.\n\n"
        f"## 4. Best Partnership Formats\n"
        f"- Prioritize product collaborations that match {', '.join(content['food_types'][:3]) or 'food and lifestyle'} content verticals.\n"
        f"- Use review + real-life scenario testing + candid feedback instead of pure scripted endorsement.\n"
        f"- Start with a single sponsored feature or a short series, then scale based on engagement quality and audience response.\n\n"
        f"## 5. Content Optimization Suggestions for the Creator\n"
        f"- Strengthen the hook in titles with clearer conflict, value, or scene-setting to improve click intent.\n"
        f"- Add sharper comment prompts to increase high-quality audience interaction.\n"
        f"- Double down on top-performing topics and turn them into repeatable content series that brands can reuse.\n\n"
        f"## 6. Missing Data\n"
        f"- More complete commerce conversion data and audience-profile information.\n"
        f"- Video-level retention, CTR, and deeper audience breakdowns.\n"
        f"- Historical performance data from past brand collaborations, including sentiment and conversion outcomes."
    )
