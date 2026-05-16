from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

import requests


def _get_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _get_request_timeout() -> int:
    raw_value = os.environ.get("YTMETRICS_REQUEST_TIMEOUT", "6").strip()
    try:
        return max(5, int(raw_value))
    except ValueError:
        return 6


def _normalize_proxy_url(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    value = raw_value.strip()
    if not value:
        return None
    if "://" not in value:
        return f"socks5h://{value}"
    if value.startswith("socks5://"):
        return value.replace("socks5://", "socks5h://", 1)
    return value


def _build_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = _get_bool_env("YTMETRICS_USE_ENV_PROXY", False)
    socks_proxy = _normalize_proxy_url(os.environ.get("YTMETRICS_SOCKS_PROXY"))
    if socks_proxy:
        session.proxies.update({"http": socks_proxy, "https": socks_proxy})
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "YTMetrics/1.0",
        }
    )
    return session


class YouTubeAPIError(RuntimeError):
    pass


class _ListRequest:
    def __init__(self, client: "YouTubeDataAPIClient", resource: str, params: dict[str, Any]):
        self.client = client
        self.resource = resource
        self.params = params

    def execute(self) -> dict[str, Any]:
        return self.client.request(self.resource, self.params)


class _ResourceProxy:
    def __init__(self, client: "YouTubeDataAPIClient", resource: str):
        self.client = client
        self.resource = resource

    def list(self, **params: Any) -> _ListRequest:
        return _ListRequest(self.client, self.resource, params)


class YouTubeDataAPIClient:
    base_url = "https://www.googleapis.com/youtube/v3/"

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        timeout: int | None = None,
    ):
        if not api_key or not api_key.strip():
            raise ValueError("YOUTUBE_API_KEY 不能为空")
        self.api_key = api_key.strip()
        self.session = session or _build_session()
        self.timeout = timeout or _get_request_timeout()

    def channels(self) -> _ResourceProxy:
        return _ResourceProxy(self, "channels")

    def search(self) -> _ResourceProxy:
        return _ResourceProxy(self, "search")

    def playlistItems(self) -> _ResourceProxy:
        return _ResourceProxy(self, "playlistItems")

    def videos(self) -> _ResourceProxy:
        return _ResourceProxy(self, "videos")

    def commentThreads(self) -> _ResourceProxy:
        return _ResourceProxy(self, "commentThreads")

    def request(self, resource: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = dict(params)
        payload["key"] = self.api_key
        url = urljoin(self.base_url, resource)

        try:
            response = self.session.get(url, params=payload, timeout=self.timeout)
        except requests.exceptions.ProxyError as exc:
            raise YouTubeAPIError(
                "无法通过当前代理连接 YouTube Data API。"
                " 如果你不需要代理，请删除 .env 中的 HTTP_PROXY / HTTPS_PROXY，"
                "或保持 YTMETRICS_USE_ENV_PROXY=false。"
            ) from exc
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as exc:
            raise YouTubeAPIError(
                f"连接 YouTube Data API 超时（>{self.timeout}s）。"
                " 请检查当前网络，或确认代理配置是否正确。"
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise YouTubeAPIError(f"YouTube Data API 请求失败: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise YouTubeAPIError("YouTube Data API 返回了无法解析的响应。") from exc

        if response.status_code >= 400:
            message = data.get("error", {}).get("message") or response.text[:200]
            raise YouTubeAPIError(
                f"YouTube Data API 返回 HTTP {response.status_code}: {message}"
            )

        if "error" in data:
            message = data["error"].get("message", "未知错误")
            raise YouTubeAPIError(f"YouTube Data API 业务错误: {message}")

        return data
