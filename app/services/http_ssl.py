"""Shared TLS settings for httpx (Python 3.13+ / httpx 0.28+)."""

from __future__ import annotations

import ssl

import certifi

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def default_ssl_context() -> ssl.SSLContext:
    return _SSL_CONTEXT
