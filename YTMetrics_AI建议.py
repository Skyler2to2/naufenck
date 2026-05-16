from __future__ import annotations
import json
import os

import requests

from ytmetrics_ai_adapter import (
    build_ai_payload,
    build_rule_based_fallback,
    render_payload_prompt,
)


class YTMetricsAI:
    def __init__(self):
        self.api_key = (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
        self.socks_proxy = self._normalize_proxy(os.environ.get("YTMETRICS_SOCKS_PROXY"))

        if os.environ.get("DEEPSEEK_API_KEY"):
            default_base_url = "https://api.deepseek.com"
            default_model = "deepseek-v4-flash"
        else:
            default_base_url = "https://api.openai.com/v1"
            default_model = "gpt-4o-mini"

        self.base_url = (os.environ.get("OPENAI_BASE_URL") or default_base_url).strip()
        self.model = (os.environ.get("OPENAI_MODEL") or default_model).strip()
        self.session = requests.Session()
        self.session.trust_env = False
        if self.socks_proxy:
            self.session.proxies.update({"http": self.socks_proxy, "https": self.socks_proxy})
        self.session.headers.update({"Content-Type": "application/json"})

    @staticmethod
    def _normalize_proxy(raw_value: str | None) -> str | None:
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

    def generate_recommendations(
        self,
        channel_info,
        content_analysis=None,
        growth_data=None,
        sentiment_summary=None,
        extra_sections=None,
    ):
        if content_analysis is None and isinstance(channel_info, dict) and "channel" in channel_info:
            payload = channel_info
        else:
            payload = build_ai_payload(
                channel_info=channel_info,
                content_analysis=content_analysis,
                growth_data=growth_data,
                sentiment_summary=sentiment_summary,
                extra_sections=extra_sections,
            )

        if not self.api_key:
            return build_rule_based_fallback(payload)

        try:
            response = self.session.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a rigorous YouTube brand-collaboration analyst. Output in English only. Conclusions must be explicit and recommendations must be actionable.",
                        },
                        {"role": "user", "content": render_payload_prompt(payload)},
                    ],
                    "temperature": 0.4,
                },
                timeout=(20, 90),
            )
            response.raise_for_status()
            data = response.json()
            return (data["choices"][0]["message"].get("content") or "").strip()
        except Exception as exc:
            return build_rule_based_fallback(payload, error_message=str(exc))
