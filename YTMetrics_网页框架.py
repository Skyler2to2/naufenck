from __future__ import annotations
import html
import io
import os
from datetime import datetime
from pathlib import Path

import jieba.analyse
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from wordcloud import WordCloud

from YTMetrics_AI建议 import YTMetricsAI
from YTMetrics_基础数据 import (
    EXAMPLE_CHANNELS,
    aggregate_recent_engagement,
    build_growth_data,
    extract_food_types,
    load_data,
    parse_channel_input,
    prepare_time_data,
)
from ytmetrics_ai_adapter import build_ai_payload, extract_top_keywords
from ytmetrics_motion import inject_motion
from ytmetrics_network import (
    apply_proxy,
    resolve_network_status,
    save_runtime_config,
    test_proxy,
)
from ytmetrics_sentiment_core import (
    YTCommentScraper,
    cached_analyze_comments,
    get_sentiment_engine,
    get_sentiment_label,
)
from ytmetrics_youtube_client import YouTubeDataAPIClient


ENV_STATUS = {"loaded": False, "message": ".env file not detected"}
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        ENV_STATUS = {"loaded": True, "message": ".env file loaded"}
    else:
        ENV_STATUS = {"loaded": False, "message": ".env file not found"}
except ImportError:
    ENV_STATUS = {"loaded": False, "message": "python-dotenv library missing"}


DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_CN = {
    "Monday": "周一",
    "Tuesday": "周二",
    "Wednesday": "周三",
    "Thursday": "周四",
    "Friday": "周五",
    "Saturday": "周六",
    "Sunday": "周日",
}
DAY_LABELS = DAY_ORDER
TIME_OPTIONS = {30: "Last month", 90: "Last 3 months", 180: "Last 6 months", 365: "Last year"}

# 有趣且活泼的新配色方案
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

# matplotlib颜色循环
COLOR_CYCLE = [
    COLOR_PALETTE["neon_pink"],
    COLOR_PALETTE["electric_blue"],
    COLOR_PALETTE["vibrant_orange"],
    COLOR_PALETTE["lime_green"],
    COLOR_PALETTE["hot_magenta"],
    COLOR_PALETTE["turquoise"],
    COLOR_PALETTE["sunshine_yellow"],
    COLOR_PALETTE["lavender"]
]

# 配置中文字体
if os.name == "nt":
    # Windows
    _CN_FONT = "Microsoft YaHei"
    plt.rcParams["font.sans-serif"] = [_CN_FONT, "SimHei", "DejaVu Sans"]
else:
    # macOS 或 Linux
    # 尝试多个 macOS 常用中文字体
    possible_fonts = [
        "Arial Unicode MS",
        "PingFang SC",
        "Hiragino Sans GB",
        "STHeiti",
        "SimHei",
        "DejaVu Sans",
    ]
    found_font = None
    for font in possible_fonts:
        try:
            from matplotlib.font_manager import findfont, FontProperties
            findfont(FontProperties(family=font))
            found_font = font
            break
        except:
            continue
    if found_font:
        _CN_FONT = found_font
    else:
        _CN_FONT = "DejaVu Sans"
    plt.rcParams["font.sans-serif"] = [_CN_FONT, "SimHei", "DejaVu Sans"]

plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["axes.prop_cycle"] = plt.cycler(color=COLOR_CYCLE)
plt.rcParams["figure.facecolor"] = COLOR_PALETTE["cream_white"]
plt.rcParams["axes.facecolor"] = COLOR_PALETTE["cream_white"]


def _proxy_port_text(proxy_url: str | None) -> str:
    if not proxy_url:
        return ""
    tail = proxy_url.rsplit(":", 1)[-1]
    return tail if tail.isdigit() else ""


def _initialize_session_state():
    if "page" not in st.session_state:
        st.session_state.page = "home"
    if "dashboard_payload" not in st.session_state:
        st.session_state.dashboard_payload = None
    if "used_mock" not in st.session_state:
        st.session_state.used_mock = False
    if "errors" not in st.session_state:
        st.session_state.errors = []
    if "channel_text" not in st.session_state:
        st.session_state.channel_text = ""
    if "analysis_status" not in st.session_state:
        st.session_state.analysis_status = None
    if "analysis_message" not in st.session_state:
        st.session_state.analysis_message = ""
    if "analysis_error_message" not in st.session_state:
        st.session_state.analysis_error_message = ""
    if "network_status" not in st.session_state:
        st.session_state.network_status = resolve_network_status()
    if "proxy_input" not in st.session_state:
        st.session_state.proxy_input = _proxy_port_text(st.session_state.network_status.proxy_url) or "1180"
    if "network_gate_ready" not in st.session_state:
        st.session_state.network_gate_ready = False


def render_network_gate():
    status = st.session_state.network_status
    st.subheader("Network Check")
    st.caption("Check if your computer can access Google / YouTube API before proceeding.")

    if status.ok:
        if status.mode == "proxy":
            st.success(f"Connected. You may proceed. Current proxy: {status.proxy_url}")
        else:
            st.success("Connected. You may proceed. Your network can access Google API directly.")

        if st.button("Continue", width="stretch", type="primary"):
            st.session_state.network_gate_ready = True
            st.rerun()
        return False

    st.error(status.message)
    st.write("If not connected, just enter your local SOCKS5 proxy port and test.")
    proxy_value = st.text_input(
        "SOCKS5 Port",
        key="proxy_input",
        help="Only enter the port number, e.g., 1180 or 7897.",
        placeholder="1180",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Test Proxy", width="stretch", type="primary"):
            tested = test_proxy(proxy_value)
            if tested.ok:
                save_runtime_config(tested.proxy_url)
                apply_proxy(tested.proxy_url)
                st.session_state.network_status = resolve_network_status()
                st.session_state.proxy_input = _proxy_port_text(
                    st.session_state.network_status.proxy_url
                ) or proxy_value.strip()
                st.session_state.network_gate_ready = True
            else:
                st.session_state.network_status = tested
                st.session_state.network_gate_ready = False
            st.rerun()
    with col2:
        if st.button("Retry Check", width="stretch"):
            st.session_state.network_status = resolve_network_status()
            if st.session_state.network_status.proxy_url:
                st.session_state.proxy_input = _proxy_port_text(
                    st.session_state.network_status.proxy_url
                )
            st.rerun()
    return False


def _render_home_sidebar():
    with st.sidebar:
        if ENV_STATUS["loaded"]:
            st.success(f"✅ {ENV_STATUS['message']}")
        else:
            st.warning(f"⚠️ {ENV_STATUS['message']}")

        status = st.session_state.get("network_status")
        if status and status.ok:
            if status.mode == "proxy":
                st.info(f"🌐 Current proxy: {status.proxy_url}")
            else:
                st.info("🌐 Direct access to Google / YouTube API available")


def _render_analysis_status(slot, message: str):
    safe_message = html.escape(message)
    slot.markdown(
        f"""
        <style>
        @keyframes ytmetricsStatusSweep {{
            0% {{
                background-position: 200% center;
                opacity: 0.78;
            }}
            50% {{
                opacity: 1;
            }}
            100% {{
                background-position: -20% center;
                opacity: 0.78;
            }}
        }}
        .ytmetrics-status-region {{
            width: 100%;
            display: flex;
            justify-content: center;
            margin-top: 18px;
            margin-bottom: 8px;
        }}
        .ytmetrics-status-card {{
            width: min(100%, 720px);
            min-height: 92px;
            padding: 22px 28px;
            border-radius: 18px;
            background: rgba(248, 250, 252, 0.96);
            border: 1px solid rgba(148, 163, 184, 0.18);
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .ytmetrics-status-text {{
            font-size: clamp(22px, 2.2vw, 32px);
            font-weight: 700;
            letter-spacing: 0.08em;
            text-align: center;
            line-height: 1.35;
            background: linear-gradient(90deg, #667085 0%, #f8fbff 48%, #667085 100%);
            background-size: 220% auto;
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            animation: ytmetricsStatusSweep 1.8s linear infinite;
        }}
        </style>
        <div class="ytmetrics-status-region">
            <div class="ytmetrics-status-card">
                <div class="ytmetrics-status-text">{safe_message}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_analysis_trace(slot, steps: list[str]):
    if not steps:
        slot.empty()
        return
    # 只显示最新的 1-2 个步骤，让显示更简洁
    latest_steps = steps[-2:]
    slot.markdown(f"**In progress:** {latest_steps[-1]}")


def _reset_analysis_feedback():
    st.session_state.analysis_status = None
    st.session_state.analysis_message = ""
    st.session_state.analysis_error_message = ""


def _safe_int(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def humanize_time(iso_date_str: str) -> str:
    try:
        published_at = pd.to_datetime(iso_date_str, utc=True, errors="coerce")
        if pd.isna(published_at):
            return str(iso_date_str)[:10]
        now = pd.Timestamp.utcnow()
        diff = now - published_at
        if diff.days > 365:
            return f"{diff.days // 365} years ago"
        if diff.days > 30:
            return f"{diff.days // 30} months ago"
        if diff.days > 0:
            return f"{diff.days} days ago"
        hours = int(diff.total_seconds() // 3600)
        minutes = int(diff.total_seconds() // 60)
        if hours > 0:
            return f"{hours} hours ago"
        if minutes > 0:
            return f"{minutes} minutes ago"
        return "just now"
    except Exception:
        return str(iso_date_str)[:10]


def highlight_best(series: pd.Series):
    is_max = series == series.max()
    return ["background-color: #e6ffe6; font-weight: bold" if flag else "" for flag in is_max]


def detect_outliers(series: pd.Series, multiplier: float = 2.0) -> tuple[pd.Series, float, float]:
    if series.empty:
        return pd.Series(dtype=bool), 0.0, 0.0
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return pd.Series(False, index=series.index), float(series.max()), float(series.min())
    upper = float(q3 + multiplier * iqr)
    lower = float(q1 - multiplier * iqr)
    mask = (series > upper) | (series < lower)
    return mask, upper, lower


def _style_ax(ax, title: str, ylabel: str, x_rotation: int = 0):
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=x_rotation)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    # 设置背景为透明
    ax.set_facecolor("none")


def _set_transparent_background(fig):
    """设置图表背景为透明"""
    fig.set_facecolor("none")


def _bar_labels(ax, bars, values, offset: float = 0.3):
    for bar, value in zip(bars, values):
        if value > 0:
            label = str(int(value)) if float(value).is_integer() else f"{value:.1f}"
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + offset,
                label,
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )


def _cap_yaxis(ax, values, upper_fence, top_ratio: float = 1.25):
    if len(values) == 0:
        ax.set_ylim(0, 1)
        return
    max_value = max(values)
    ceiling = upper_fence if upper_fence and not pd.isna(upper_fence) else max_value * top_ratio if max_value > 0 else 1
    ax.set_ylim(0, ceiling * top_ratio)


def load_example_channels():
    st.session_state.channel_text = EXAMPLE_CHANNELS


def _build_content_analysis(channel_data: dict) -> dict:
    recent_videos = channel_data.get("recent_videos", [])
    titles = [video.get("title", "") for video in recent_videos]
    food_types = extract_food_types(titles)
    top_keywords = extract_top_keywords(titles, limit=4)

    total_views = sum(int(video.get("views", 0)) for video in recent_videos)
    total_engagement = sum(
        int(video.get("likes", 0)) + int(video.get("comments", 0)) for video in recent_videos
    )
    engagement_rate = round(total_engagement / total_views * 100, 2) if total_views else 0.0

    return {
        "food_types": food_types,
        "engagement_rate": engagement_rate,
        "top_video_themes": top_keywords or ["Food review", "Local exploration"],
    }


def _collect_global_comment_records(channel_data_list: list[dict], api_key: str, status_callback=None) -> list[dict]:
    if not api_key:
        return []
    scraper = YTCommentScraper(api_key)
    cached_records: list[dict] = []

    for channel in channel_data_list:
        channel_name = channel.get("channel_name", "Unknown")
        for video in channel.get("recent_videos", []):
            video_id = str(video.get("id", ""))
            stored = scraper.data.get(video_id, {})
            for comment in stored.get("comments", []):
                cached_records.append(
                    {
                        "Channel": channel_name,
                        "Video Title": str(video.get("title", "")),
                        "评论者": str(comment.get("author", "")),
                        "评论内容": str(comment.get("text", "")),
                        "👍 点赞": _safe_int(comment.get("like_count", 0)),
                        "发布时间": humanize_time(str(comment.get("published_at", ""))),
                        "published_at_raw": str(comment.get("published_at", "")),
                    }
                )

    if cached_records:
        return cached_records

    youtube = YouTubeDataAPIClient(api_key)
    all_videos: list[tuple[str, dict]] = []

    for channel in channel_data_list:
        for video in channel.get("recent_videos", []):
            if video.get("id"):
                all_videos.append((channel.get("channel_name", "Unknown"), video))

    raw_comments: list[dict] = []
    total_videos = len(all_videos)
    for index, (channel_name, video) in enumerate(all_videos, start=1):
        if status_callback:
            status_callback(f"Fetching comments ({index}/{total_videos}): {channel_name}")
        scraper.scrape_comments(
            youtube,
            str(video.get("id", "")),
            str(video.get("title", "")),
            max_comments=100,
        )
        stored = scraper.data.get(str(video.get("id", "")), {})
        for comment in stored.get("comments", []):
            raw_comments.append(
                {
                    "Channel": channel_name,
                    "Video Title": str(video.get("title", "")),
                    "评论者": str(comment.get("author", "")),
                    "评论内容": str(comment.get("text", "")),
                    "👍 点赞": _safe_int(comment.get("like_count", 0)),
                    "发布时间": humanize_time(str(comment.get("published_at", ""))),
                    "published_at_raw": str(comment.get("published_at", "")),
                }
            )
    return raw_comments


def _analyze_global_sentiment(raw_comments: list[dict], status_callback=None) -> dict:
    sentiment_result = {
        "display_comments": [],
        "all_comments": [],
        "raw_comments": raw_comments,
        "neg_ratio": 0.0,
        "neg_count": 0,
        "total_display": 0,
        "has_sentiment": False,
    }
    if not raw_comments:
        return sentiment_result

    engine = get_sentiment_engine()
    ranked_comments = sorted(raw_comments, key=lambda item: item.get("👍 点赞", 0), reverse=True)[:30]

    if status_callback:
        status_callback("Analyzing top comments sentiment…")

    analysis_results = cached_analyze_comments(
        engine,
        tuple(comment["评论内容"] for comment in ranked_comments),
        version="zip-global-sentiment-v1",
    )

    analyzed_comments: list[dict] = []
    for raw, analysis in zip(ranked_comments, analysis_results):
        if analysis is None:
            continue
        analyzed_comments.append(
            {
                **raw,
                "情感评分": round(analysis["score"], 2),
                "情感倾向": analysis["label"],
                "置信度": analysis["confidence"],
                "is_negative": analysis["score"] < -0.2,
            }
        )

    if not analyzed_comments:
        return sentiment_result

    neg_count = sum(1 for comment in analyzed_comments if comment["is_negative"])
    total_display = len(analyzed_comments)
    sentiment_result.update(
        {
            "display_comments": analyzed_comments,
            "all_comments": analyzed_comments,
            "raw_comments": raw_comments,
            "neg_ratio": round(neg_count / total_display * 100, 1),
            "neg_count": neg_count,
            "total_display": total_display,
            "has_sentiment": True,
        }
    )
    return sentiment_result


def _build_channel_sentiment_summary(channel_name: str, analyzed_comments: list[dict]) -> dict:
    summary = {
        "label": "中性 (Neutral)",
        "score": 0.0,
        "neg_ratio": 0.0,
        "top_keywords": [],
    }
    channel_comments = [comment for comment in analyzed_comments if comment.get("Channel") == channel_name]
    if not channel_comments:
        return summary

    avg_score = sum(comment["情感评分"] for comment in channel_comments) / len(channel_comments)
    neg_count = sum(1 for comment in channel_comments if comment["is_negative"])
    label, _ = get_sentiment_label(avg_score)
    summary.update(
        {
            "label": label,
            "score": round(avg_score, 2),
            "neg_ratio": round(neg_count / len(channel_comments) * 100, 1),
            "top_keywords": extract_top_keywords(
                [comment["评论内容"] for comment in channel_comments],
                limit=5,
            ),
        }
    )
    return summary


def _build_dashboard_payload(channel_data_list: list[dict], used_mock: bool, errors: list[str], status_callback) -> dict:
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    has_baidu = all(
        bool(os.environ.get(key, "").strip())
        for key in ["BAIDU_APP_ID", "BAIDU_API_KEY", "BAIDU_SECRET_KEY"]
    )
    global_sentiment = {
        "display_comments": [],
        "all_comments": [],
        "raw_comments": [],
        "neg_ratio": 0.0,
        "neg_count": 0,
        "total_display": 0,
        "has_sentiment": False,
    }

    if not used_mock and api_key:
        try:
            raw_comments = _collect_global_comment_records(channel_data_list, api_key, status_callback)
            global_sentiment["raw_comments"] = raw_comments
            if has_baidu:
                global_sentiment = _analyze_global_sentiment(raw_comments, status_callback)
        except Exception as exc:
            errors = list(errors) + [f"Comment fetching/sentiment analysis failed, skipping word cloud: {exc}"]
    elif not has_baidu:
        errors = list(errors) + ["Baidu sentiment analysis credentials not configured, sentiment word cloud disabled."]
    if not has_baidu:
        errors = list(errors) + ["When Baidu sentiment analysis is not configured, comment corpus and keyword preview will be shown first."]

    ai_engine = YTMetricsAI()
    channel_bundles = []
    total_channels = len(channel_data_list)

    for index, channel in enumerate(channel_data_list, start=1):
        status_callback(f"Organizing channel analysis ({index}/{total_channels}): {channel.get('channel_name', 'Unknown')}")
        content_analysis = _build_content_analysis(channel)
        growth_data = build_growth_data(channel)
        sentiment_summary = _build_channel_sentiment_summary(
            channel.get("channel_name", ""),
            global_sentiment.get("all_comments", []),
        )
        ai_payload = build_ai_payload(
            channel_info=channel,
            content_analysis=content_analysis,
            growth_data=growth_data,
            sentiment_summary=sentiment_summary,
        )
        ai_suggestion = ai_engine.generate_recommendations(ai_payload)
        channel_bundles.append(
            {
                "channel": channel,
                "content": content_analysis,
                "growth": growth_data,
                "sentiment": sentiment_summary,
                "ai_payload": ai_payload,
                "ai_suggestion": ai_suggestion,
            }
        )

    return {
        "channels": channel_bundles,
        "used_mock": used_mock,
        "errors": errors,
        "global_sentiment": global_sentiment,
    }


def _run_analysis_flow(identifiers: list[str]):
    identifiers = [identifier.strip() for identifier in identifiers if identifier and identifier.strip()]
    if not identifiers:
        st.session_state.analysis_status = "error"
        st.session_state.analysis_error_message = "Please enter at least one channel link, @handle, or Channel ID."
        st.error(st.session_state.analysis_error_message)
        return False

    _reset_analysis_feedback()
    st.session_state.dashboard_payload = None
    st.session_state.errors = []
    st.session_state.used_mock = False
    st.session_state.analysis_status = "running"
    st.session_state.page = "home"

    st.caption(f"Submitted {len(identifiers)} channels")
    status_slot = st.empty()
    progress_bar = st.progress(0, text="Preparing analysis")
    trace_slot = st.empty()
    steps: list[str] = []

    def update_status(message: str):
        clean_message = (message or "").strip() or "Analyzing…"
        if not steps or steps[-1] != clean_message:
            steps.append(clean_message)
        st.session_state.analysis_message = clean_message
        _render_analysis_status(status_slot, clean_message)
        progress_bar.progress(min(len(steps) * 8, 94))
        _render_analysis_trace(trace_slot, steps)

    update_status("Checking network and environment…")
    network_status = resolve_network_status()
    if not network_status.ok:
        st.session_state.analysis_status = "error"
        st.session_state.analysis_error_message = network_status.message
        progress_bar.empty()
        st.error(st.session_state.analysis_error_message)
        return False

    try:
        update_status("Fetching channel data…")
        channel_data_list, used_mock, errors = load_data(identifiers)
        if not channel_data_list:
            raise RuntimeError("No available channel data.")

        payload = _build_dashboard_payload(channel_data_list, used_mock, errors, update_status)
    except Exception as exc:
        st.session_state.analysis_status = "error"
        st.session_state.analysis_message = ""
        st.session_state.analysis_error_message = f"Error during analysis: {exc}"
        progress_bar.empty()
        st.error(st.session_state.analysis_error_message)
        return False

    update_status("Analysis complete, opening results…")
    progress_bar.progress(100, text="Analysis complete")
    st.session_state.dashboard_payload = payload
    st.session_state.used_mock = payload.get("used_mock", False)
    st.session_state.errors = payload.get("errors", [])
    st.session_state.analysis_status = "success"
    st.session_state.analysis_message = ""
    st.session_state.analysis_error_message = ""
    st.session_state.network_status = network_status
    st.session_state.page = "dashboard"
    st.rerun()
    return True


def go_to_home():
    st.session_state.page = "home"
    st.session_state.dashboard_payload = None
    st.session_state.errors = []
    _reset_analysis_feedback()


def _render_summary_table(channel_bundles: list[dict]):
    rows = []
    for bundle in channel_bundles:
        channel = bundle["channel"]
        videos = channel.get("recent_videos", [])
        eng7 = aggregate_recent_engagement(videos, 7)
        eng30 = aggregate_recent_engagement(videos, 30)
        food_types = extract_food_types([video.get("title", "") for video in videos])

        rows.append(
            {
                "Channel ID": channel.get("channel_id", ""),
                "Channel": channel.get("channel_name", ""),
                "Subscribers": _safe_int(channel.get("subscribers", 0)),
                "Videos": _safe_int(channel.get("video_count", 0)),
                "Total Views": _safe_int(channel.get("view_count", 0)),
                "7d Engagement (👍+💬)": eng7["likes"] + eng7["comments"],
                "7d Source": "Last 7 days" if eng7["source"] == "recent" else "Top video fallback",
                "30d Engagement (👍+💬)": eng30["likes"] + eng30["comments"],
                "30d Source": "Last 30 days" if eng30["source"] == "recent" else "Top video fallback",
                "Food Types": ", ".join(food_types) or "—",
            }
        )

    summary_df = pd.DataFrame(rows)
    st.subheader("📊 Summary Table", anchor="summary-metrics")
    st.dataframe(
        summary_df,
        use_container_width=True,
        column_config={
            "Subscribers": st.column_config.NumberColumn(format="%d"),
            "Videos": st.column_config.NumberColumn(format="%d"),
            "Total Views": st.column_config.NumberColumn(format="%d"),
            "7d Engagement (👍+💬)": st.column_config.NumberColumn(format="%d"),
            "30d Engagement (👍+💬)": st.column_config.NumberColumn(format="%d"),
        },
        hide_index=True,
    )
    csv_bytes = summary_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Download CSV",
        data=csv_bytes,
        file_name="hk_food_youtubers.csv",
        mime="text/csv",
    )


def _render_channel_details(channel_bundles: list[dict]):
    st.subheader("🔍 Channel Details", anchor="channel-details")
    for bundle in channel_bundles:
        channel = bundle["channel"]
        videos = channel.get("recent_videos", [])
        eng7 = aggregate_recent_engagement(videos, 7)
        eng30 = aggregate_recent_engagement(videos, 30)
        food_types = bundle["content"].get("food_types", [])

        with st.expander(
            f"📌 {channel.get('channel_name', 'Unknown')}  ·  {channel.get('channel_id', '')}",
            expanded=False,
        ):
            c1, c2, c3 = st.columns(3)
            c1.metric("Subscribers", f"{_safe_int(channel.get('subscribers', 0)):,}")
            c2.metric("Total Videos", f"{_safe_int(channel.get('video_count', 0)):,}")
            c3.metric("Total Views", f"{_safe_int(channel.get('view_count', 0)):,}")

            c1, c2 = st.columns(2)
            with c1:
                if eng7["source"] == "recent":
                    st.markdown(f"**Last 7 days engagement** ({eng7['video_count']} videos)")
                elif eng7["source"] == "top":
                    st.markdown("**No new videos in last 7 days, falling back to top liked video**")
                    st.caption(f"《{eng7['top_title']}》")
                else:
                    st.markdown("**Last 7 days**: No data")
                st.write(f"👍 {eng7['likes']:,}  ·  💬 {eng7['comments']:,}")

            with c2:
                if eng30["source"] == "recent":
                    st.markdown(f"**Last 30 days engagement** ({eng30['video_count']} videos)")
                elif eng30["source"] == "top":
                    st.markdown("**No new videos in last 30 days, falling back to top liked video**")
                    st.caption(f"《{eng30['top_title']}》")
                else:
                    st.markdown("**Last 30 days**: No data")
                st.write(f"👍 {eng30['likes']:,}  ·  💬 {eng30['comments']:,}")

            st.markdown(f"**🍜 Food types covered:** {', '.join(food_types) if food_types else 'Not identified'}")

            if videos:
                st.markdown("**Recent videos:**")
                video_df = pd.DataFrame(videos)
                visible_columns = [
                    column
                    for column in ["published", "title", "views", "likes", "comments"]
                    if column in video_df
                ]
                rename_map = {
                    "published": "Published",
                    "title": "Title",
                    "views": "👀",
                    "likes": "👍",
                    "comments": "💬",
                }
                st.dataframe(
                    video_df[visible_columns].rename(columns=rename_map),
                    use_container_width=True,
                    hide_index=True,
                )


def _render_time_dimension_analysis(channel_bundles: list[dict]):
    st.subheader("⏰ Time Dimension Analysis", anchor="time-dimension-analysis")
    time_window_days = st.select_slider(
        "Analysis Time Range",
        options=list(TIME_OPTIONS.keys()),
        value=365,
        format_func=lambda days: f"{TIME_OPTIONS[days]}",
    )

    all_time_videos = []
    for bundle in channel_bundles:
        channel = bundle["channel"]
        for video in channel.get("recent_videos", []):
            all_time_videos.append({**video, "channel": channel.get("channel_name", "Unknown")})

    if not all_time_videos:
        st.info("No video data available for time dimension analysis. Please load channel data first.")
        return

    time_df = prepare_time_data(all_time_videos).sort_values("published_date")
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=time_window_days)
    time_df_full = time_df.copy()
    time_df = time_df[time_df["published_date"] >= cutoff]

    if time_df.empty:
        st.info("No video data available in the current time window.")
        return

    filtered_count = len(time_df_full) - len(time_df)
    date_min = time_df["published_date"].min().strftime("%Y-%m-%d")
    date_max = time_df["published_date"].max().strftime("%Y-%m-%d")
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    channel_names = sorted({video["channel"] for video in all_time_videos})
    channel_count = len(channel_names)

    channel_frames = {}
    for channel_name in channel_names:
        channel_videos = [video for video in all_time_videos if video["channel"] == channel_name]
        channel_df = prepare_time_data(channel_videos)
        channel_frames[channel_name] = channel_df[channel_df["published_date"] >= cutoff].sort_values("published_date")

    day_counts = time_df["day_of_week"].value_counts().reindex(range(7), fill_value=0)
    day_stats = time_df.groupby("day_of_week").agg(
        Videos=("engagement", "count"),
        Avg_likes=("likes", "mean"),
        Avg_comments=("comments", "mean"),
        Avg_engagement=("engagement", "mean"),
    ).reindex(range(7), fill_value=0)
    day_stats.index = DAY_LABELS
    month_counts = time_df.groupby("year_month").size()

    outlier_mask, engagement_upper, _ = detect_outliers(time_df["engagement"])
    outlier_videos = time_df[outlier_mask].sort_values("engagement", ascending=False)
    has_outliers = len(outlier_videos) > 0

    st.markdown("### 📈 Publishing Cadence Overview")
    total_videos = len(time_df)
    date_range = (time_df["published_date"].max() - time_df["published_date"].min()).days
    avg_interval = round(date_range / max(total_videos - 1, 1), 1)
    best_day_idx = day_stats["Avg_engagement"].idxmax() if not day_stats.empty else DAY_LABELS[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Total videos ({TIME_OPTIONS[time_window_days]})", f"{total_videos}")
    c2.metric("Avg. publishing interval", f"{avg_interval} days")
    c3.metric("Time span", f"{date_range} days")
    c4.metric("Best engagement day", best_day_idx)
    if filtered_count > 0:
        st.caption(
            f"📅 Analysis window: {cutoff_str} → {date_max} (rolling {time_window_days} days) | "
            f"Channel's earliest video: {date_min} | ⏳ Filtered {filtered_count} older videos"
        )
    else:
        st.caption(f"📅 Analysis window: {cutoff_str} → {date_max} (rolling {time_window_days} days) | Channel's earliest video: {date_min}")

    st.markdown("### 📅 Video Publishing Frequency Distribution")
    if channel_count > 1:
        tab_freq_all, tab_freq_channel = st.tabs(["📊 Overview", "🔍 By Channel"])
    else:
        tab_freq_all = st.container()
        tab_freq_channel = None

    with tab_freq_all:
        col_a, col_b = st.columns(2)
        with col_a:
            fig, ax = plt.subplots(figsize=(5, 3.5))
            _set_transparent_background(fig)
            # 使用多彩配色
            bar_colors = [COLOR_CYCLE[i % len(COLOR_CYCLE)] for i in range(len(day_counts))]
            bars = ax.bar(DAY_LABELS, day_counts.values, color=bar_colors, width=0.6)
            _bar_labels(ax, bars, day_counts.values)
            _style_ax(ax, "All channels · Day of week distribution", "Videos")
            ax.set_ylim(0, max(day_counts.values) * 1.25 if max(day_counts.values) > 0 else 1)
            st.pyplot(fig)
            plt.close(fig)

        with col_b:
            if len(month_counts) > 0:
                fig, ax = plt.subplots(figsize=(5, 3.5))
                _set_transparent_background(fig)
                months = month_counts.index.tolist()
                values = month_counts.values.tolist()
                ax.plot(months, values, marker="o", color=COLOR_PALETTE["deep_blue"], linewidth=2, markersize=8)
                for x_value, y_value in zip(months, values):
                    ax.text(x_value, y_value + 0.3, str(y_value), ha="center", fontsize=9, fontweight="bold")
                _style_ax(ax, "All channels · Monthly trend", "Videos", x_rotation=30)
                st.pyplot(fig)
                plt.close(fig)
            else:
                st.info("Not enough monthly data")

    if tab_freq_channel is not None:
        with tab_freq_channel:
            channel_day_rows = []
            for channel_name in channel_names:
                channel_df = channel_frames[channel_name]
                for day_index in range(7):
                    channel_day_rows.append(
                        {
                            "Channel": channel_name,
                            "Day": DAY_LABELS[day_index],
                            "Videos": int((channel_df["day_of_week"] == day_index).sum()),
                        }
                    )
            if channel_day_rows:
                pivot_df = pd.DataFrame(channel_day_rows).pivot_table(
                    index="Day",
                    columns="Channel",
                    values="Videos",
                    fill_value=0,
                ).reindex(DAY_LABELS)
                fig, ax = plt.subplots(figsize=(10, 3.5 + 0.3 * channel_count))
                _set_transparent_background(fig)
                pivot_df.plot(kind="bar", ax=ax, width=0.75)
                _style_ax(ax, "By channel · Day of week distribution", "Videos")
                ax.legend(title="Channel", fontsize=8, bbox_to_anchor=(1.02, 1), loc="upper left")
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
                st.dataframe(pivot_df, use_container_width=True)
            else:
                st.info("Not enough data per channel")

    st.markdown("### 📈 Engagement Over Time")
    if channel_count > 1:
        tab_trend_all, tab_trend_channel = st.tabs(["📊 Overview", "🔍 By Channel"])
    else:
        tab_trend_all = st.container()
        tab_trend_channel = None

    with tab_trend_all:
        col_a, col_b = st.columns(2)
        with col_a:
            fig, ax = plt.subplots(figsize=(5, 3.5))
            _set_transparent_background(fig)
            ax.plot(
                time_df["published_date"],
                time_df["engagement"],
                marker="o",
                color=COLOR_PALETTE["bright_pink"],
                linewidth=2,
                markersize=8,
            )
            if has_outliers:
                ax.axhline(
                    y=engagement_upper,
                    color=COLOR_PALETTE["orange"],
                    linestyle="--",
                    alpha=0.7,
                    label=f"Outlier upper bound ({int(engagement_upper):,})",
                )
                ax.legend(fontsize=8)
                _cap_yaxis(ax, time_df["engagement"].values, engagement_upper)
            _style_ax(ax, "All channels · Engagement trend", "Likes + Comments", x_rotation=30)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

        with col_b:
            fig, ax = plt.subplots(figsize=(5, 3.5))
            _set_transparent_background(fig)
            engagement_max = max(float(time_df["engagement"].max()), 1.0)
            scatter = ax.scatter(
                time_df["published_date"],
                time_df["engagement"],
                s=time_df["engagement"] / engagement_max * 300 + 30,
                c=time_df["likes"],
                cmap="viridis",
                alpha=0.7,
                edgecolors=COLOR_PALETTE["deep_blue"],
                linewidth=0.5,
            )
            if has_outliers:
                ax.axhline(y=engagement_upper, color=COLOR_PALETTE["orange"], linestyle="--", alpha=0.7)
                _cap_yaxis(ax, time_df["engagement"].values, engagement_upper)
            _style_ax(ax, "All channels · Engagement scatter (color=lots)", "Engagement", x_rotation=30)
            plt.colorbar(scatter, ax=ax, label="Like count")
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

        if has_outliers:
            with st.expander(f"🔍 View {len(outlier_videos)} outlier videos"):
                st.dataframe(
                    outlier_videos[["published_date", "channel", "title", "engagement", "likes", "comments"]].rename(
                        columns={
                            "published_date": "Published date",
                            "channel": "Channel",
                            "title": "Title",
                            "engagement": "Engagement",
                            "likes": "👍",
                            "comments": "💬",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

    if tab_trend_channel is not None:
        with tab_trend_channel:
            cols = 2
            for row_index in range((channel_count + 1) // 2):
                row_columns = st.columns(cols)
                for col_index in range(cols):
                    channel_index = row_index * cols + col_index
                    if channel_index >= channel_count:
                        break
                    channel_name = channel_names[channel_index]
                    channel_df = channel_frames[channel_name]
                    with row_columns[col_index]:
                        if channel_df.empty:
                            st.info(f"{channel_name} has no data in current time window")
                            continue
                        channel_outliers, channel_upper, _ = detect_outliers(channel_df["engagement"])
                        fig, ax = plt.subplots(figsize=(5, 2.8))
                        _set_transparent_background(fig)
                        ax.plot(
                            channel_df["published_date"],
                            channel_df["engagement"],
                            marker="o",
                            color="#E8724A",
                            linewidth=2,
                            markersize=6,
                        )
                        if channel_outliers.any():
                            ax.axhline(y=channel_upper, color="gray", linestyle="--", alpha=0.6, linewidth=1)
                            _cap_yaxis(ax, channel_df["engagement"].values, channel_upper)
                        _style_ax(ax, channel_name, "Engagement", x_rotation=30)
                        fig.tight_layout()
                        st.pyplot(fig)
                        plt.close(fig)

    st.markdown("### 🎯 Best Publishing Day Analysis")
    if channel_count > 1:
        tab_best_all, tab_best_channel = st.tabs(["📊 Overview", "🔍 By Channel"])
    else:
        tab_best_all = st.container()
        tab_best_channel = None

    with tab_best_all:
        day_stats_display = day_stats.round(0).astype(int)
        st.dataframe(
            day_stats_display.style.apply(highlight_best, subset=["Avg_engagement"]),
            use_container_width=True,
        )

        col_a, col_b = st.columns(2)
        with col_a:
            _, day_upper, _ = detect_outliers(day_stats["Avg_engagement"])
            fig, ax = plt.subplots(figsize=(5, 3.5))
            _set_transparent_background(fig)
            best_value = day_stats["Avg_engagement"].max()
            # 使用多彩配色，最佳日用高亮颜色
            colors = [
                COLOR_PALETTE["bright_yellow"] if value == best_value 
                else COLOR_CYCLE[i % len(COLOR_CYCLE)] 
                for i, value in enumerate(day_stats["Avg_engagement"].values)
            ]
            bars = ax.bar(DAY_LABELS, day_stats["Avg_engagement"].values, color=colors, width=0.6)
            _bar_labels(ax, bars, day_stats["Avg_engagement"].values, offset=5)
            _style_ax(ax, "All channels · Average engagement by day", "Avg Engagement")
            _cap_yaxis(ax, day_stats["Avg_engagement"].values, day_upper)
            st.pyplot(fig)
            plt.close(fig)

        with col_b:
            fig, ax = plt.subplots(figsize=(5, 3.5))
            _set_transparent_background(fig)
            # 使用多彩配色
            bar_colors = [COLOR_CYCLE[i % len(COLOR_CYCLE)] for i in range(len(day_stats))]
            bars = ax.bar(DAY_LABELS, day_stats["Videos"].values, color=bar_colors, width=0.6)
            _bar_labels(ax, bars, day_stats["Videos"].values)
            _style_ax(ax, "All channels · Publishing count by day", "Videos")
            st.pyplot(fig)
            plt.close(fig)

    if tab_best_channel is not None:
        with tab_best_channel:
            best_rows = []
            channel_compare_rows = []
            for channel_name in channel_names:
                channel_df = channel_frames[channel_name]
                channel_stats = channel_df.groupby("day_of_week").agg(
                    Videos=("engagement", "count"),
                    Avg_engagement=("engagement", "mean"),
                ).reindex(range(7), fill_value=0)
                best_idx = channel_stats["Avg_engagement"].idxmax()
                best_rows.append(
                    {
                        "Channel": channel_name,
                        "Best posting day": DAY_LABELS[best_idx],
                        "Best day avg engagement": int(channel_stats.loc[best_idx, "Avg_engagement"]),
                        "Most frequent posting day": DAY_LABELS[channel_stats["Videos"].idxmax()],
                    }
                )
                for day_index in range(7):
                    channel_compare_rows.append(
                        {
                            "Channel": channel_name,
                            "Day": DAY_LABELS[day_index],
                            "Avg_engagement": round(channel_stats.loc[day_index, "Avg_engagement"], 0),
                            "Videos": int(channel_stats.loc[day_index, "Videos"]),
                        }
                    )

            if best_rows:
                st.dataframe(pd.DataFrame(best_rows), use_container_width=True, hide_index=True)

            if channel_compare_rows:
                compare_pivot = pd.DataFrame(channel_compare_rows).pivot_table(
                    index="Day",
                    columns="Channel",
                    values="Avg_engagement",
                    fill_value=0,
                ).reindex(DAY_LABELS)
                fig, ax = plt.subplots(figsize=(10, 3.5 + 0.3 * channel_count))
                _set_transparent_background(fig)
                compare_pivot.plot(kind="bar", ax=ax, width=0.75)
                _style_ax(ax, "By channel · Average engagement comparison by day", "Avg Engagement")
                ax.legend(title="Channel", fontsize=8, bbox_to_anchor=(1.02, 1), loc="upper left")
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)

    st.markdown("### ⏱️ Publishing Interval Analysis")
    interval_rows = []
    for channel_name in channel_names:
        channel_df = channel_frames[channel_name]
        if len(channel_df) >= 2:
            dates_sorted = channel_df.sort_values("published_date")["published_date"]
            gaps = [
                (dates_sorted.iloc[index] - dates_sorted.iloc[index - 1]).days
                for index in range(1, len(dates_sorted))
            ]
            avg_gap = sum(gaps) / len(gaps)
            interval_rows.append(
                {
                    "Channel": channel_name,
                    "Videos": len(channel_df),
                    "Min interval (days)": min(gaps),
                    "Max interval (days)": max(gaps),
                    "Avg interval (days)": round(avg_gap, 1),
                    "Publishing stability": "High frequency stable" if max(gaps) <= 7 else "Occasional gaps" if max(gaps) <= 21 else "Sparse publishing",
                }
            )

    if interval_rows:
        st.dataframe(pd.DataFrame(interval_rows), use_container_width=True, hide_index=True)


def _render_sentiment_analysis(global_sentiment: dict):
    st.subheader("🎭 Sentiment Analysis & Word Cloud", anchor="sentiment-analysis")
    raw_comments = global_sentiment.get("raw_comments", [])
    display_comments = global_sentiment.get("display_comments", [])
    has_sentiment = bool(global_sentiment.get("has_sentiment"))

    if not raw_comments and not display_comments:
        st.info("💡 No comment data yet, please complete channel analysis first.")
        return

    if raw_comments:
        preview_df = pd.DataFrame(
            sorted(raw_comments, key=lambda item: item.get("👍 点赞", 0), reverse=True)[:100]
        )
        st.markdown("### 💬 Top Comments Preview")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Comments collected", f"{len(raw_comments):,}")
        col_b.metric("Top comment samples", f"{len(preview_df):,}")
        col_c.metric("Channels covered", f"{preview_df['Channel'].nunique() if not preview_df.empty and 'Channel' in preview_df else 0}")

        keyword_source = " ".join(preview_df["评论内容"].astype(str).tolist()) if not preview_df.empty else ""
        preview_keywords = jieba.analyse.extract_tags(keyword_source, topK=20)
        if preview_keywords:
            st.caption("Keyword preview: " + " / ".join(preview_keywords))

        st.dataframe(
            preview_df[["Channel", "Video Title", "评论者", "👍 点赞", "发布时间", "评论内容"]]
            if not preview_df.empty
            else preview_df,
            use_container_width=True,
            hide_index=True,
        )

    if not has_sentiment:
        st.info("When Baidu sentiment analysis has not produced results yet, show comment corpus preview first. Sentiment word cloud and negative ratio will be shown after successful sentiment analysis.")
        return

    neg_ratio = float(global_sentiment.get("neg_ratio", 0.0))
    neg_count = int(global_sentiment.get("neg_count", 0))
    total_display = int(global_sentiment.get("total_display", 0))

    col_a, col_b = st.columns([1, 2])
    with col_a:
        st.metric("Negative ratio", f"{neg_ratio:.1f}%", delta_color="inverse")
    with col_b:
        st.progress(neg_ratio / 100 if neg_ratio else 0.0)
        st.caption(f"Showing {neg_count} negative comments out of top {total_display}")

    st.markdown("### ☁️ Sentiment Word Cloud")
    with st.spinner("Generating word cloud..."):
        all_text_for_cloud = " ".join(comment["评论内容"] for comment in display_comments)
        jieba_keywords = jieba.analyse.extract_tags(all_text_for_cloud, topK=80, withWeight=True)
        word_freq = {word: weight for word, weight in jieba_keywords}

        if word_freq:
            word_colors = {}
            # 有趣的新配色方案
            wc_colors = [
                COLOR_PALETTE["neon_pink"],
                COLOR_PALETTE["electric_blue"],
                COLOR_PALETTE["vibrant_orange"],
                COLOR_PALETTE["lime_green"],
                COLOR_PALETTE["hot_magenta"],
                COLOR_PALETTE["turquoise"],
                COLOR_PALETTE["sunshine_yellow"],
            ]
            for i, word in enumerate(word_freq):
                word_colors[word] = wc_colors[i % len(wc_colors)]

            def color_func(word, **kwargs):
                return word_colors.get(word, COLOR_PALETTE["gray"])

            # 找到合适的中文字体路径
            font_path = None
            if os.name == "nt":
                # Windows
                font_path = "msyh.ttc"
            else:
                # macOS/Linux
                possible_font_paths = [
                    "/System/Library/Fonts/PingFang.ttc",
                    "/System/Library/Fonts/STHeiti Light.ttc",
                    "/System/Library/Fonts/Hiragino Sans GB.ttc",
                    "/Library/Fonts/Arial Unicode.ttf",
                ]
                for path in possible_font_paths:
                    if os.path.exists(path):
                        font_path = path
                        break
            
            word_cloud = WordCloud(
                font_path=font_path,
                background_color=None,
                mode="RGBA",
                width=1000,
                height=500,
                max_words=80,
                relative_scaling=0.5,
                color_func=color_func,
            ).generate_from_frequencies(word_freq)

            fig, ax = plt.subplots(figsize=(10, 5))
            _set_transparent_background(fig)
            ax.imshow(word_cloud, interpolation="bilinear")
            ax.axis("off")
            st.pyplot(fig)

            img_buffer = io.BytesIO()
            fig.savefig(img_buffer, format="png", bbox_inches="tight", dpi=300, transparent=True)
            st.download_button(
                label="🖼️ Export Word Cloud (PNG)",
                data=img_buffer.getvalue(),
                file_name="sentiment_wordcloud.png",
                mime="image/png",
            )
            plt.close(fig)
        else:
            st.warning("⚠️ Not enough comments to generate word cloud.")

    st.markdown("### 🧐 Sentiment Word Distribution")
    with st.spinner("Analyzing word sentiment..."):
        all_text_for_cloud = " ".join(comment["评论内容"] for comment in display_comments)
        jieba_keywords = jieba.analyse.extract_tags(all_text_for_cloud, topK=50, withWeight=True)

        chart_data = []
        for word, weight in jieba_keywords:
            word_scores = [comment["情感评分"] for comment in display_comments if word in comment["评论内容"]]
            if word_scores:
                avg_score = sum(word_scores) / len(word_scores)
                chart_data.append(
                    {
                        "Keyword": word,
                        "Frequency": weight * 100,
                        "Sentiment_score": avg_score,
                        "Sentiment_polarity": "Positive" if avg_score > 0.2 else "Negative" if avg_score < -0.2 else "Neutral",
                    }
                )

        if chart_data:
            chart_df = pd.DataFrame(chart_data)
            st.scatter_chart(
                chart_df,
                x="Sentiment_score",
                y="Frequency",
                color="Sentiment_polarity",
                size="Frequency",
                use_container_width=True,
            )
            selected_word = st.selectbox("🎯 Quick filter by keyword:", ["All"] + [item["Keyword"] for item in chart_data])
            display_df = pd.DataFrame(display_comments)
            if selected_word != "All":
                display_df = display_df[display_df["评论内容"].str.contains(selected_word, na=False)]
            st.caption("💡 Tip: X-axis shows sentiment (left negative, right positive), bubble size shows word frequency.")
        else:
            display_df = pd.DataFrame(display_comments)
            st.warning("⚠️ Not enough word frequency data to generate analysis chart.")

    st.dataframe(
        display_df.drop(columns=["is_negative"], errors="ignore"),
        use_container_width=True,
        column_config={
            "情感评分": st.column_config.NumberColumn(format="%.2f"),
            "置信度": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=1),
            "评论内容": st.column_config.TextColumn(width="large"),
        },
        hide_index=True,
    )

    st.markdown("### 📥 Export Data")
    csv_data = pd.DataFrame(display_comments).to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="💾 Download Full Sentiment Report (CSV)",
        data=csv_data,
        file_name=f"Sentiment_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True,
    )


def _render_ai_analysis(channel_bundles: list[dict]):
    st.subheader("🫧 AI Analysis", anchor="ai-analysis")
    for bundle in channel_bundles:
        channel = bundle["channel"]
        with st.expander(f"🤖 {channel.get('channel_name', 'Unknown')} · AI Analysis", expanded=False):
            st.markdown(bundle.get("ai_suggestion", "No AI analysis available yet."))


def main():
    st.set_page_config(
        page_title="YTMetrics - YouTuber Analysis",
        page_icon="📊",
        layout="wide",
    )

    # 注入 DDNA 风格动效与微交互(零功能侵入,详见 ytmetrics_motion.py)
    inject_motion()

    # 全局CSS样式 - 有趣且时尚的新设计
    st.markdown(
        f"""
        <style>
        .stApp {{
            background: linear-gradient(135deg, {COLOR_PALETTE['cream_white']} 0%, {COLOR_PALETTE['lavender']} 100%);
            background-attachment: fixed;
        }}
        
        /* 标题样式 - 有趣的渐变和动画 */
        h1 {{
            background: linear-gradient(45deg, {COLOR_PALETTE['neon_pink']}, {COLOR_PALETTE['electric_blue']}, {COLOR_PALETTE['vibrant_orange']});
            background-size: 200% 200%;
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent !important;
            animation: gradientShift 3s ease infinite;
            font-weight: 900 !important;
            letter-spacing: -1px;
        }}
        
        h2 {{
            background: linear-gradient(90deg, {COLOR_PALETTE['electric_blue']}, {COLOR_PALETTE['turquoise']});
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent !important;
            font-weight: 800 !important;
            position: relative;
            display: inline-block;
        }}
        
        h2::after {{
            content: '';
            position: absolute;
            bottom: -5px;
            left: 0;
            width: 100%;
            height: 3px;
            background: linear-gradient(90deg, {COLOR_PALETTE['neon_pink']}, {COLOR_PALETTE['sunshine_yellow']});
            border-radius: 2px;
        }}
        
        h3 {{
            color: {COLOR_PALETTE['deep_purple']} !important;
            font-weight: 700 !important;
            font-style: italic;
        }}
        
        @keyframes gradientShift {{
            0%, 100% {{ background-position: 0% 50%; }}
            50% {{ background-position: 100% 50%; }}
        }}
        
        /* 按钮样式 - 有趣的3D效果和动画 */
        button[kind="primary"] {{
            background: linear-gradient(135deg, {COLOR_PALETTE['neon_pink']}, {COLOR_PALETTE['hot_magenta']}) !important;
            color: white !important;
            border: none !important;
            border-radius: 50px !important;
            font-weight: 700 !important;
            letter-spacing: 1px;
            box-shadow: 0 4px 15px rgba(255, 0, 110, 0.4);
            transition: all 0.3s ease !important;
        }}
        
        button[kind="primary"]:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(255, 0, 110, 0.6);
            background: linear-gradient(135deg, {COLOR_PALETTE['electric_blue']}, {COLOR_PALETTE['turquoise']}) !important;
        }}
        
        /* 普通按钮 */
        button[kind="secondary"] {{
            border: 2px solid {COLOR_PALETTE['electric_blue']} !important;
            color: {COLOR_PALETTE['electric_blue']} !important;
            border-radius: 50px !important;
            font-weight: 600 !important;
            background: transparent !important;
            transition: all 0.3s ease !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }}
        
        button[kind="secondary"]:hover {{
            background: linear-gradient(135deg, {COLOR_PALETTE['sunshine_yellow']}, {COLOR_PALETTE['vibrant_orange']}) !important;
            border-color: transparent !important;
            color: white !important;
            transform: scale(1.02);
        }}
        
        /* 所有按钮文本不溢出 */
        button, button[kind="primary"], button[kind="secondary"] {{
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            min-width: fit-content !important;
        }}
        
        /* 滑块样式 */
        div[data-testid="stSliderThumbValue"] {{
            background: linear-gradient(135deg, {COLOR_PALETTE['neon_pink']}, {COLOR_PALETTE['vibrant_orange']}) !important;
            color: white !important;
            font-weight: bold;
            box-shadow: 0 2px 8px rgba(255, 0, 110, 0.4);
        }}
        
        div[role="slider"] {{
            background: linear-gradient(90deg, {COLOR_PALETTE['neon_pink']}, {COLOR_PALETTE['electric_blue']}) !important;
        }}
        
        div.stSlider > div > div > div {{
            background: {COLOR_PALETTE['lavender']} !important;
        }}
        
        /* 侧边栏 - 有趣的渐变背景 */
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {COLOR_PALETTE['cream_white']} 0%, {COLOR_PALETTE['soft_mint']} 100%) !important;
            border-right: 3px solid {COLOR_PALETTE['turquoise']};
        }}
        
        /* 输入框样式 */
        input[type="text"], textarea {{
            border: 2px solid {COLOR_PALETTE['electric_blue']} !important;
            border-radius: 15px !important;
            background: {COLOR_PALETTE['cream_white']} !important;
            transition: all 0.3s ease !important;
        }}
        
        input[type="text"]:focus, textarea:focus {{
            border-color: {COLOR_PALETTE['neon_pink']} !important;
            box-shadow: 0 0 15px rgba(255, 0, 110, 0.2);
        }}
        
        /* 下拉菜单 */
        div[data-testid="stSelectbox"] > div {{
            border: 2px solid {COLOR_PALETTE['lime_green']} !important;
            border-radius: 15px !important;
        }}
        
        /* 数据表格样式 */
        div[data-testid="stDataFrame"] {{
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
            background: transparent !important;
        }}
        
        /* 数据表格内部背景透明 */
        div[data-testid="stDataFrame"] div,
        div[data-testid="stDataFrame"] table {{
            background: transparent !important;
        }}
        
        /* 数据编辑器背景透明 */
        div[data-testid="stDataFrameGlideDataEditor"] {{
            background: transparent !important;
        }}
        
        /* Streamlit 图表容器背景透明 */
        div[data-testid="stImageContainer"],
        div[data-testid="stImage"] {{
            background: transparent !important;
        }}
        
        /* Streamlit pyplot 图表背景透明 */
        div[data-testid="stPyplotContainer"] {{
            background: transparent !important;
        }}
        
        /* 数据编辑器的所有内部元素背景透明 */
        div[data-testid="stDataFrameGlideDataEditor"] * {{
            background: transparent !important;
        }}
        
        /* Glide 数据编辑器特定样式 */
        .dvn-scroller {{
            background: transparent !important;
        }}
        
        .dvn-scroll-inner {{
            background: transparent !important;
        }}
        
        .dvn-stack {{
            background: transparent !important;
        }}
        
        /* SVG 元素背景透明 */
        svg {{
            background: transparent !important;
        }}
        
        /* 表格行和单元格背景透明 */
        .glideDataEditor__cell {{
            background: transparent !important;
        }}
        
        .glideDataEditor__cell--header {{
            background: transparent !important;
        }}
        
        /* 完整的 Glide Data Editor 样式 */
        .glideDataEditor {{
            background: transparent !important;
        }}
        
        .glideDataEditor__viewport {{
            background: transparent !important;
        }}
        
        /* Streamlit 表格容器所有子元素 */
        [data-testid="stDataFrame"] * {{
            background: transparent !important;
        }}
        
        /* 额外的表格元素样式 */
        [data-baseweb="data-table"] {{
            background: transparent !important;
        }}
        
        [data-baseweb="data-table"] * {{
            background: transparent !important;
        }}
        
        /* 分隔线 */
        hr {{
            border: none;
            height: 3px;
            background: linear-gradient(90deg, transparent, {COLOR_PALETTE['neon_pink']}, {COLOR_PALETTE['electric_blue']}, {COLOR_PALETTE['sunshine_yellow']}, transparent);
            margin: 2rem 0;
        }}
        
        /* 卡片容器 */
        .stBlockContainer {{
            background: rgba(255, 252, 249, 0.9);
            border-radius: 20px;
            padding: 1.5rem;
            margin: 1rem 0;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
        }}
        
        /* 指标卡片样式 */
        div[data-testid="stMetric"] {{
            background: linear-gradient(135deg, {COLOR_PALETTE['cream_white']}, {COLOR_PALETTE['lavender']});
            border-radius: 15px;
            padding: 1rem;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.08);
            border: 1px solid {COLOR_PALETTE['turquoise']};
        }}
        
        /* 标签页样式 */
        button[data-baseweb="tab"] {{
            border-radius: 15px 15px 0 0 !important;
            font-weight: 600 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }}
        
        button[data-baseweb="tab"][aria-selected="true"] {{
            background: linear-gradient(135deg, {COLOR_PALETTE['electric_blue']}, {COLOR_PALETTE['turquoise']}) !important;
            color: white !important;
        }}
        
        /* 展开/收起按钮 */
        div[data-testid="stExpander"] {{
            border-radius: 15px !important;
            border: 2px solid {COLOR_PALETTE['soft_mint']} !important;
            overflow: hidden;
        }}
        
        div[data-testid="stExpander"] > div:first-child {{
            background: linear-gradient(135deg, {COLOR_PALETTE['soft_mint']}, {COLOR_PALETTE['turquoise']});
        }}
        
        /* 警告和成功消息 */
        .stSuccess {{
            background: linear-gradient(135deg, {COLOR_PALETTE['lime_green']}, {COLOR_PALETTE['soft_mint']}) !important;
            border-radius: 15px !important;
            border: none !important;
            color: {COLOR_PALETTE['dark_charcoal']} !important;
        }}
        
        .stWarning {{
            background: linear-gradient(135deg, {COLOR_PALETTE['sunshine_yellow']}, {COLOR_PALETTE['vibrant_orange']}) !important;
            border-radius: 15px !important;
            border: none !important;
            color: {COLOR_PALETTE['dark_charcoal']} !important;
        }}
        
        .stError {{
            background: linear-gradient(135deg, {COLOR_PALETTE['hot_magenta']}, {COLOR_PALETTE['neon_pink']}) !important;
            border-radius: 15px !important;
            border: none !important;
            color: white !important;
        }}
        
        /* 信息消息 */
        .stInfo {{
            background: linear-gradient(135deg, {COLOR_PALETTE['electric_blue']}, {COLOR_PALETTE['lavender']}) !important;
            border-radius: 15px !important;
            border: none !important;
            color: white !important;
        }}
        
        /* 文件上传器 */
        section[data-testid="stFileUploader"] {{
            border: 3px dashed {COLOR_PALETTE['electric_blue']} !important;
            border-radius: 20px !important;
            background: {COLOR_PALETTE['cream_white']} !important;
        }}
        
        /* 进度条 */
        div[data-testid="stProgress"] > div > div {{
            background: linear-gradient(90deg, {COLOR_PALETTE['neon_pink']}, {COLOR_PALETTE['electric_blue']}, {COLOR_PALETTE['sunshine_yellow']}) !important;
            border-radius: 10px !important;
        }}
        
        /* 滑块样式 - 防止文本溢出 */
        div[data-testid="stSelectSlider"] {{
            padding: 0.5rem 0;
        }}
        
        div[data-testid="stSelectSlider"] [data-baseweb="slider"] {{
            padding: 0 1rem;
        }}
        
        /* 滑块数值标签 */
        [data-testid="stSliderThumbValue"] {{
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            font-size: 0.85rem !important;
            padding: 0.25rem 0.5rem !important;
        }}
        
        /* 下载按钮 */
        .stDownloadButton button {{
            background: linear-gradient(135deg, {COLOR_PALETTE['turquoise']}, {COLOR_PALETTE['lime_green']}) !important;
            color: white !important;
            border: none !important;
            border-radius: 50px !important;
            font-weight: 700 !important;
        }}
        
        .stDownloadButton button:hover {{
            background: linear-gradient(135deg, {COLOR_PALETTE['lime_green']}, {COLOR_PALETTE['turquoise']}) !important;
            transform: translateY(-2px);
        }}
        </style>
        """,
        unsafe_allow_html=True
    )
    
    _initialize_session_state()

    if not st.session_state.network_gate_ready:
        # 添加有趣的装饰元素
        st.markdown(
            f"""
            <div style="text-align: center; padding: 2rem 0;">
                <div style="font-size: 4rem; animation: bounce 2s infinite;">
                    🍜 🎬 📊
                </div>
                <style>
                @keyframes bounce {{
                    0%, 20%, 50%, 80%, 100% {{ transform: translateY(0); }}
                    40% {{ transform: translateY(-20px); }}
                    60% {{ transform: translateY(-10px); }}
                }}
                </style>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        st.title("📊 YTMetrics")
        st.subheader("Turn Hong Kong Food Channels into Actionable Insights")
        st.markdown("---")

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            render_network_gate()
        st.stop()

    if st.session_state.page == "home":
        # 添加有趣的装饰元素
        st.markdown(
            f"""
            <div style="text-align: center; padding: 1rem 0;">
                <div style="display: flex; justify-content: center; gap: 1rem; font-size: 2.5rem;">
                    <span style="animation: float 3s ease-in-out infinite;">🍜</span>
                    <span style="animation: float 3s ease-in-out infinite 0.5s;">🥢</span>
                    <span style="animation: float 3s ease-in-out infinite 1s;">🎬</span>
                    <span style="animation: float 3s ease-in-out infinite 1.5s;">📊</span>
                    <span style="animation: float 3s ease-in-out infinite 2s;">🌟</span>
                </div>
                <style>
                @keyframes float {{
                    0%, 100% {{ transform: translateY(0px); }}
                    50% {{ transform: translateY(-15px); }}
                }}
                </style>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        st.title("📊 YTMetrics — HK Food YouTuber Analysis")
        st.subheader("Turn Hong Kong Food Channels into Actionable Insights")
        st.markdown("---")

        _render_home_sidebar()

        api_key_present = bool(os.environ.get("YOUTUBE_API_KEY", "").strip())
        if api_key_present:
            st.success("✅ `YOUTUBE_API_KEY` detected, will use YouTube Data API to fetch real-time data")
        else:
            st.warning("⚠️ `YOUTUBE_API_KEY` not set, will use built-in mock sample data")

        tab_text, tab_csv = st.tabs(["📝 Paste Channels", "📂 Upload CSV"])

        with tab_text:
            col_btn1, col_btn2 = st.columns([1, 3])
            with col_btn1:
                st.button(
                    "🍜 Load HK food example",
                    on_click=load_example_channels,
                    use_container_width=True,
                )
            with col_btn2:
                st.caption(
                    "Examples: 點 Cook Guide, Stephen Leung, Alfred Chan, "
                    "Taylor R, Chef Joe HK, Mill MILK (real HK food/lifestyle channels)"
                )

            channel_text = st.text_area(
                "One Channel URL / @handle / Channel ID per line",
                height=220,
                placeholder=(
                    "https://www.youtube.com/@channel_handle\n"
                    "@another_handle\n"
                    "UCxxxxxxxxxxxxxxxxxxxxxx"
                ),
                key="channel_text",
            )
            if st.button("Analyze", use_container_width=True, key="btn_text", type="primary"):
                identifiers = parse_channel_input(channel_text)
                _run_analysis_flow(identifiers)

        with tab_csv:
            uploaded = st.file_uploader(
                "Upload CSV with `channel` column (URL / @handle / ID)",
                type=["csv"],
            )
            if uploaded is not None:
                try:
                    input_df = pd.read_csv(uploaded)
                    column_name = "channel" if "channel" in input_df.columns else input_df.columns[0]
                    identifiers = input_df[column_name].dropna().astype(str).tolist()
                    st.write(f"Loaded {len(identifiers)} channels, preview:")
                    st.dataframe(input_df.head(10), use_container_width=True)
                    if st.button("Analyze CSV", use_container_width=True, key="btn_csv", type="primary"):
                        _run_analysis_flow(identifiers)
                except Exception as exc:
                    st.error(f"Failed to read CSV: {exc}")

        if st.session_state.analysis_status == "error" and st.session_state.analysis_error_message:
            st.error(st.session_state.analysis_error_message)

    elif st.session_state.page == "dashboard":
        payload = st.session_state.dashboard_payload or {}
        channel_bundles = payload.get("channels", [])

        # 添加有趣的装饰元素
        st.markdown(
            f"""
            <div style="text-align: center; padding: 0.5rem 0;">
                <div style="display: flex; justify-content: center; gap: 0.8rem; font-size: 2rem;">
                    <span style="animation: spin 4s linear infinite;">📈</span>
                    <span style="animation: pulse 2s ease-in-out infinite;">🎯</span>
                    <span style="animation: spin 4s linear infinite reverse;">💡</span>
                </div>
                <style>
                @keyframes spin {{
                    from {{ transform: rotate(0deg); }}
                    to {{ transform: rotate(360deg); }}
                }}
                @keyframes pulse {{
                    0%, 100% {{ transform: scale(1); }}
                    50% {{ transform: scale(1.2); }}
                }}
                </style>
            </div>
            """,
            unsafe_allow_html=True
        )

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
                - [⏰ Time Dimension Analysis](#time-dimension-analysis)
                - [🎭 Sentiment Analysis](#sentiment-analysis)
                - [🫧 AI Analysis](#ai-analysis)
                """
            )

        st.title("HK Food YouTuber Dashboard")
        if payload.get("used_mock"):
            st.info("Currently showing **mock example data**. Set the environment variable `YOUTUBE_API_KEY` and restart to fetch real-time data.")
        for message in payload.get("errors", []):
            st.warning(message)
        st.markdown("---")

        if not channel_bundles:
            st.warning("No data to display")
        else:
            _render_summary_table(channel_bundles)
            st.markdown("---")
            _render_channel_details(channel_bundles)
            st.markdown("---")
            _render_time_dimension_analysis(channel_bundles)
            st.markdown("---")
            _render_sentiment_analysis(payload.get("global_sentiment", {}))
            st.markdown("---")
            _render_ai_analysis(channel_bundles)

        st.markdown("---")
        st.caption("Powered by YTMetrics")
