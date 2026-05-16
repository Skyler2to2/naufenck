from __future__ import annotations

import json
import os
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests


CONFIG_PATH = Path.home() / ".ytmetrics" / "runtime.json"
GOOGLE_PROBE_URL = "https://www.googleapis.com/discovery/v1/apis?name=youtube&preferred=true"
COMMON_SOCKS_PORTS = [7890, 7891, 7892, 7897, 7898, 1080, 1081, 10808, 10809, 1180, 2080, 2081]


@dataclass
class NetworkStatus:
    ok: bool
    mode: str
    proxy_url: str | None
    message: str
    source: str


def _normalize_proxy_url(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if "://" not in raw:
        return f"socks5h://{raw}"
    if raw.startswith("socks5://"):
        return raw.replace("socks5://", "socks5h://", 1)
    return raw


def _build_proxy_url(port_value: str | int | None) -> str | None:
    if port_value is None:
        return None
    raw = str(port_value).strip()
    if not raw:
        return None
    if raw.isdigit():
        return f"socks5h://127.0.0.1:{raw}"
    return _normalize_proxy_url(raw)


def load_runtime_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_runtime_config(proxy_url: str | None):
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"proxy_url": proxy_url or ""}
        CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _extract_host_port(proxy_url: str | None) -> tuple[str, int] | None:
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    if not parsed.hostname or not parsed.port:
        return None
    return parsed.hostname, parsed.port


def _is_local_port_open(host: str, port: int, timeout: float = 0.35) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        sock.close()


def _list_local_listening_ports() -> set[int]:
    commands = [
        ["powershell", "-NoProfile", "-Command", "Get-NetTCPConnection -State Listen | Select-Object -ExpandProperty LocalPort"],
        ["netstat", "-ano", "-p", "tcp"],
    ]
    ports: set[int] = set()
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
        except Exception:
            continue
        if completed.stdout:
            for raw_line in completed.stdout.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.isdigit():
                    ports.add(int(line))
                    continue
                if ":" in line and "LISTENING" in line.upper():
                    maybe_port = line.split()[1].rsplit(":", 1)[-1]
                    if maybe_port.isdigit():
                        ports.add(int(maybe_port))
    return ports


def _discover_candidate_ports() -> list[int]:
    listening_ports = _list_local_listening_ports()
    preferred_ports = [port for port in COMMON_SOCKS_PORTS if port in listening_ports]
    dynamic_ports = sorted(
        port
        for port in listening_ports
        if 1000 <= port <= 20000 and port not in COMMON_SOCKS_PORTS
    )
    return preferred_ports + dynamic_ports + [port for port in COMMON_SOCKS_PORTS if port not in preferred_ports]


def _probe(proxy_url: str | None, timeout: float = 1.8) -> tuple[bool, str]:
    host_port = _extract_host_port(proxy_url)
    if host_port and not _is_local_port_open(host_port[0], host_port[1]):
        return False, f"本机端口 {host_port[1]} 未监听，代理未启动或端口不对。"
    session = requests.Session()
    session.trust_env = False
    if proxy_url:
        session.proxies.update({"http": proxy_url, "https": proxy_url})
    try:
        response = session.get(GOOGLE_PROBE_URL, timeout=timeout)
        if response.status_code < 500:
            return True, f"Google API 可访问（HTTP {response.status_code}）"
        return False, f"Google API 返回异常状态码：{response.status_code}"
    except Exception as exc:
        return False, str(exc)


def _probe_candidates(candidates: list[str], timeout: float) -> tuple[str | None, str]:
    last_message = ""
    for proxy_url in candidates:
        ok, message = _probe(proxy_url, timeout)
        if ok:
            return proxy_url, message
        last_message = message or f"{proxy_url} 不可用"
    return None, last_message


def apply_proxy(proxy_url: str | None):
    if proxy_url:
        os.environ["YTMETRICS_SOCKS_PROXY"] = proxy_url
    else:
        os.environ.pop("YTMETRICS_SOCKS_PROXY", None)


def test_proxy(proxy_input: str) -> NetworkStatus:
    proxy_url = _build_proxy_url(proxy_input)
    ok, message = _probe(proxy_url, timeout=2.4)
    return NetworkStatus(
        ok=ok,
        mode="proxy" if ok else "offline",
        proxy_url=proxy_url,
        message=message,
        source="manual_test",
    )


def resolve_network_status(
    progress_callback: Callable[[str], None] | None = None,
    *,
    use_saved_runtime: bool = False,
) -> NetworkStatus:
    def report(message: str):
        if progress_callback:
            progress_callback(message)

    runtime_proxy = _normalize_proxy_url(load_runtime_config().get("proxy_url")) if use_saved_runtime else None
    env_proxy = _normalize_proxy_url(os.environ.get("YTMETRICS_SOCKS_PROXY"))

    for proxy_url, source, label in [
        (runtime_proxy, "saved_runtime", "正在检查已保存的代理配置…"),
        (env_proxy, "env", "正在检查环境变量里的代理配置…"),
        (None, "direct", "正在检查直连网络…"),
    ]:
        if source != "direct" and not proxy_url:
            continue
        report(label)
        ok, message = _probe(proxy_url, timeout=2.0 if proxy_url else 2.2)
        if ok:
            apply_proxy(proxy_url)
            return NetworkStatus(
                ok=True,
                mode="proxy" if proxy_url else "direct",
                proxy_url=proxy_url,
                message=message,
                source=source,
            )

    candidate_ports = _discover_candidate_ports()[:8]
    candidate_urls = [f"socks5h://127.0.0.1:{port}" for port in candidate_ports]
    report(f"正在扫描本机监听中的代理端口（{len(candidate_urls)} 个候选）…")
    proxy_url, message = _probe_candidates(candidate_urls, timeout=0.9)
    if proxy_url:
        apply_proxy(proxy_url)
        return NetworkStatus(
            ok=True,
            mode="proxy",
            proxy_url=proxy_url,
            message=message,
            source="auto_detected",
        )

    apply_proxy(None)
    return NetworkStatus(
        ok=False,
        mode="offline",
        proxy_url=None,
        message="未自动检测到可用的代理或直连链路，请手动填写 SOCKS5 代理后测试。",
        source="none",
    )
