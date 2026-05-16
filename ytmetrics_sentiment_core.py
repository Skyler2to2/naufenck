from __future__ import annotations
import concurrent.futures
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("scraper.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
logging.getLogger("streamlit.runtime.scriptrunner.script_run_context").setLevel(logging.ERROR)
ua = UserAgent()


def _get_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _build_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = _get_bool_env("YTMETRICS_USE_ENV_PROXY", False)
    socks_proxy = os.environ.get("YTMETRICS_SOCKS_PROXY", "").strip()
    if socks_proxy:
        if "://" not in socks_proxy:
            socks_proxy = f"socks5h://{socks_proxy}"
        elif socks_proxy.startswith("socks5://"):
            socks_proxy = socks_proxy.replace("socks5://", "socks5h://", 1)
        session.proxies.update({"http": socks_proxy, "https": socks_proxy})
    session.headers.update({"User-Agent": "YTMetrics/1.0"})
    return session


class BilingualSentimentEngine:
    """基于百度 NLP REST API 的情感分析引擎。"""

    def __init__(self):
        self.app_id = os.environ.get("BAIDU_APP_ID", "").strip()
        self.api_key = os.environ.get("BAIDU_API_KEY", "").strip()
        self.secret_key = os.environ.get("BAIDU_SECRET_KEY", "").strip()
        self.session = _build_session()
        self.error_msg = ""
        if self.api_key and self.secret_key:
            self.access_token = self._get_access_token()
            self.ready = bool(self.access_token)
        else:
            self.access_token = None
            self.ready = False
            self.error_msg = "未配置百度情感分析凭证"
        self.rate_limit_interval = max(2.0, float(os.environ.get("YT_BAIDU_SENTIMENT_INTERVAL", "2.0")))
        self._last_sentiment_call = 0.0

    def _get_access_token(self):
        url = (
            "https://aip.baidubce.com/oauth/2.0/token"
            f"?grant_type=client_credentials&client_id={self.api_key}&client_secret={self.secret_key}"
        )
        try:
            response = self.session.get(url, timeout=8)
            res = response.json()
            if "access_token" in res:
                return res["access_token"]
            self.error_msg = f"Token 错误: {res.get('error_description', '未知错误')}"
            logger.error("Baidu Token Error: %s", res)
        except Exception as exc:
            self.error_msg = f"网络请求异常: {exc}"
            logger.error("Failed to get Baidu token: %s", exc)
        return None

    def analyze(self, text: str) -> dict | None:
        if not self.ready or not text.strip():
            return None

        url = (
            "https://aip.baidubce.com/rpc/2.0/nlp/v1/sentiment_classify"
            f"?access_token={self.access_token}"
        )
        try:
            elapsed = time.time() - self._last_sentiment_call
            if elapsed < self.rate_limit_interval:
                time.sleep(self.rate_limit_interval - elapsed)
            payload = json.dumps({"text": text[:500]})
            response = self.session.post(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            self._last_sentiment_call = time.time()
            if response.status_code != 200:
                logger.error("Baidu API HTTP Error: %s", response.status_code)
                return None
            res = response.json()
            if "items" in res:
                item = res["items"][0]
                pos_prob = item["positive_prob"]
                sentiment = item["sentiment"]
                score = (pos_prob * 2) - 1
                label_map = {0: "负面 (Negative)", 1: "中性 (Neutral)", 2: "正面 (Positive)"}
                return {
                    "score": round(score, 2),
                    "label": label_map.get(sentiment, "中性 (Neutral)"),
                    "confidence": item.get("confidence", 0.0),
                    "keywords": [],
                }
            if "error_code" in res:
                if str(res.get("error_code")) == "18":
                    logger.warning("Baidu sentiment QPS limit hit, backing off and retrying once.")
                    time.sleep(max(self.rate_limit_interval, 2.5))
                    response = self.session.post(
                        url,
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=5,
                    )
                    self._last_sentiment_call = time.time()
                    retry_res = response.json()
                    if "items" in retry_res:
                        item = retry_res["items"][0]
                        pos_prob = item["positive_prob"]
                        sentiment = item["sentiment"]
                        score = (pos_prob * 2) - 1
                        label_map = {0: "负面 (Negative)", 1: "中性 (Neutral)", 2: "正面 (Positive)"}
                        return {
                            "score": round(score, 2),
                            "label": label_map.get(sentiment, "中性 (Neutral)"),
                            "confidence": item.get("confidence", 0.0),
                            "keywords": [],
                        }
                logger.error(
                    "Baidu API Logic Error: %s (Code: %s)",
                    res.get("error_msg"),
                    res.get("error_code"),
                )
        except requests.exceptions.Timeout:
            logger.error("Baidu API Timeout for text: %s...", text[:20])
        except Exception as exc:
            logger.error("Baidu API Unexpected Error: %s", exc)
        return None

    def analyze_batch(self, texts: list[str]) -> list[dict | None]:
        if not self.ready or not texts:
            return [None] * len(texts)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return list(executor.map(self.analyze, texts))


@st.cache_resource
def get_sentiment_engine():
    return BilingualSentimentEngine()


@st.cache_data(show_spinner=False, ttl=3600)
def cached_analyze_comments(_engine, texts: list[str], version: str = "1.2"):
    if not hasattr(_engine, "analyze_batch"):
        _engine = BilingualSentimentEngine()
        if not hasattr(_engine, "analyze_batch"):
            return [None] * len(texts)
    return _engine.analyze_batch(texts)


def get_sentiment_label(score: float) -> tuple[str, str]:
    if score > 0.6:
        return "正面 (Positive)", "green"
    if score < 0.4:
        return "负面 (Negative)", "red"
    return "中性 (Neutral)", "gray"


class YTCommentScraper:
    def __init__(self, api_key: str, storage_path: str = "scraped_comments.json"):
        self.api_key = api_key
        self.storage_path = Path(storage_path)
        self.quota_used = 0
        self.max_quota = 10000
        self.last_request_time = 0
        self.rate_limit_interval = 0.6
        self.data = self._load_existing_data()

    def _load_existing_data(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as file:
                    return json.load(file)
            except Exception as exc:
                logger.error("Error loading existing data: %s", exc)
        return {}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def scrape_by_url(self, youtube, url: str, max_comments: int = 100):
        video_id = self._extract_video_id(url)
        if not video_id:
            raise ValueError(f"无效的 YouTube 链接: {url}")

        v_resp = youtube.videos().list(part="snippet", id=video_id).execute()
        if not v_resp.get("items"):
            raise Exception("无法获取视频信息，请检查链接或 API Key")
        video_title = v_resp["items"][0]["snippet"]["title"]
        self.scrape_comments(youtube, video_id, video_title, max_comments)
        return video_id

    def _extract_video_id(self, url: str) -> str | None:
        patterns = [
            r"(?:v=|/)([0-9A-Za-z_-]{11}).*",
            r"youtu\.be/([0-9A-Za-z_-]{11})",
            r"embed/([0-9A-Za-z_-]{11})",
            r"/v/([0-9A-Za-z_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def analyze_link_type(self, url: str) -> dict:
        analysis = {
            "url": url,
            "type": "未知",
            "is_secure": url.startswith("https"),
            "is_accessible": False,
            "metadata": {},
            "errors": [],
        }
        try:
            resp = self.session.head(url, headers={"User-Agent": ua.random}, timeout=3)
            analysis["is_accessible"] = resp.status_code < 400
            if "youtube.com/watch" in url or "youtu.be/" in url:
                analysis["type"] = "YouTube 视频页面"
            elif "youtube.com/@" in url or "youtube.com/channel/" in url:
                analysis["type"] = "YouTube 频道主页"
            elif "list=" in url:
                analysis["type"] = "YouTube 播放列表"
            else:
                analysis["type"] = "常规网页"
        except Exception as exc:
            analysis["errors"].append(f"访问检测失败: {exc}")
        return analysis

    def _save_data(self):
        try:
            with open(self.storage_path, "w", encoding="utf-8") as file:
                json.dump(self.data, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error("Error saving data: %s", exc)

    def _check_quota(self, cost: int):
        if self.quota_used + cost > self.max_quota:
            logger.warning("API Quota limit reached (%s). Stopping.", self.max_quota)
            raise Exception("API Quota exceeded for today")
        self.quota_used += cost

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_interval:
            time.sleep(self.rate_limit_interval - elapsed)
        self.last_request_time = time.time()

    def scrape_comments(self, youtube, video_id: str, video_title: str, max_comments: int = 100):
        if video_id in self.data and len(self.data[video_id].get("comments", [])) >= max_comments:
            logger.info("Skipping video %s (already scraped)", video_id)
            return

        self._rate_limit()
        try:
            self._check_quota(1)
            comments = []
            response = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=min(max_comments, 100),
                textFormat="plainText",
            ).execute()

            for item in response.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                comment_id = item["id"]
                if video_id in self.data:
                    existing_ids = {comment["id"] for comment in self.data[video_id].get("comments", [])}
                    if comment_id in existing_ids:
                        continue
                comments.append(
                    {
                        "id": comment_id,
                        "author": snippet["authorDisplayName"],
                        "text": snippet["textDisplay"],
                        "published_at": snippet["publishedAt"],
                        "like_count": int(snippet.get("likeCount", 0)),
                    }
                )

            if video_id not in self.data:
                self.data[video_id] = {
                    "video_title": video_title,
                    "scraped_at": datetime.now().isoformat(),
                    "comments": [],
                }

            self.data[video_id]["comments"].extend(comments)
            self._save_data()
            logger.info("Scraped %s comments for [%s]", len(comments), video_title)
        except Exception as exc:
            if "commentsDisabled" in str(exc):
                logger.warning("Comments disabled for video: %s", video_id)
                self.data[video_id] = {"video_title": video_title, "error": "Comments disabled"}
                self._save_data()
            else:
                logger.error("Error scraping %s: %s", video_id, exc)

    def get_as_df(self) -> pd.DataFrame:
        rows = []
        for video_id, info in self.data.items():
            if "comments" not in info:
                continue
            for comment in info["comments"]:
                rows.append(
                    {
                        "video_id": video_id,
                        "video_title": info["video_title"],
                        "comment_id": comment["id"],
                        "author": comment["author"],
                        "text": comment["text"],
                        "published_at": comment["published_at"],
                        "like_count": comment.get("like_count", 0),
                    }
                )
        return pd.DataFrame(rows)
