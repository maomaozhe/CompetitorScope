"""Stable identifier and canonicalization helpers for V2 domain objects."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlsplit


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def stable_id(prefix: str, value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{sha256_text(payload)}"


def normalize_official_domain(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("official_domain must not be empty")
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    host = parsed.hostname
    if not host:
        raise ValueError("official_domain must be a valid hostname")
    try:
        normalized = host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("official_domain must be a valid IDNA hostname") from exc
    if not normalized or "." not in normalized:
        raise ValueError("official_domain must contain a registrable-looking suffix")
    return normalized


def url_has_official_authority(url: str, official_domain: str) -> bool:
    host = urlsplit(url).hostname
    if not host:
        return False
    try:
        normalized_host = host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return False
    domain = normalize_official_domain(official_domain)
    return normalized_host == domain or normalized_host.endswith(f".{domain}")
