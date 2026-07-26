"""Utilities for getting WAN/public IP and building WAN URL.

No external deps: use standard library only.
"""

from __future__ import annotations

import json
import urllib.request


def get_wan_ip(timeout: float = 5.0) -> str | None:
    """Get current WAN/public IP using multiple external sources.

    Returns:
        Public IP string if any source returns successfully, else None.
    """

    ip_sources = [
        ("https://api.ipify.org", "ipify"),
        ("https://ifconfig.me/ip", "ifconfig.me"),
        ("https://icanhazip.com", "icanhazip"),
        ("https://ipapi.co/ip", "ipapi"),
    ]

    for url, _name in ip_sources:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "WMS/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="ignore").strip()

            if not body:
                continue

            # ipapi.co/ip may return plain text; but handle JSON just in case
            if body.startswith("{"):
                try:
                    parsed = json.loads(body)
                    ip = (parsed.get("ip") or parsed.get("query") or "").strip()
                    if ip:
                        return ip
                    continue
                except Exception:
                    continue

            # plain text
            return body

        except Exception:
            continue

    return None


def build_wan_url(port: int, path: str = "", protocol: str = "http") -> str | None:
    """Build WAN URL like http://{WAN_IP}:{port}{path} (or https://)."""
    ip = get_wan_ip()
    if not ip:
        return None
    if path and not path.startswith("/"):
        path = "/" + path
    return f"{protocol}://{ip}:{port}{path}".rstrip()

