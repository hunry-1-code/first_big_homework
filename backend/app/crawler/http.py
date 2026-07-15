from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import requests
from app.crawler.errors import CrawlerError


def _resolve_host(host: str) -> list[str]:
    return list(
        dict.fromkeys(
            item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        )
    )


class HttpClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        allowed_hosts: set[str] | None = None,
        timeout: int = 30,
        max_attempts: int = 3,
        max_response_bytes: int = 5 * 1024 * 1024,
        sleep: Callable[[float], None] = time.sleep,
        resolver: Callable[[str], list[str]] = _resolve_host,
        platform: str = "http",
    ) -> None:
        self.session = session or requests.Session()
        self.allowed_hosts = {host.lower() for host in (allowed_hosts or set())}
        self.timeout = max(1, int(timeout))
        self.max_attempts = max(1, int(max_attempts))
        self.max_response_bytes = max(1, int(max_response_bytes))
        self.sleep = sleep
        self.resolver = resolver
        self.platform = platform

    def get_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        return self.request_json("GET", url, **kwargs)

    def post_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        return self.request_json("POST", url, **kwargs)

    def get_text(self, url: str, **kwargs: Any) -> str:
        prefer_xml = bool(kwargs.pop("prefer_xml", False))
        response = self._request("GET", url, **kwargs)
        body = self._read_body(response)
        if prefer_xml:
            declaration = re.match(
                br"\s*<\?xml[^>]+encoding=[\"']([^\"']+)[\"']",
                body[:200],
                re.IGNORECASE,
            )
            encodings = ["utf-8-sig"]
            if declaration:
                encodings.insert(0, declaration.group(1).decode("ascii", errors="ignore"))
            for encoding in dict.fromkeys(encodings):
                try:
                    return body.decode(encoding)
                except (LookupError, UnicodeDecodeError):
                    continue
        encoding = getattr(response, "encoding", None) or "utf-8"
        return body.decode(encoding, errors="replace")

    def request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        response = self._request(method, url, **kwargs)
        try:
            payload = json.loads(self._read_body(response).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CrawlerError(
                self.platform,
                "CRAWL_INVALID_JSON",
                "response is not valid JSON",
                False,
            ) from exc
        if not isinstance(payload, dict):
            raise CrawlerError(
                self.platform,
                "CRAWL_INVALID_JSON",
                "JSON response must be an object",
                False,
            )
        return payload

    def _request(self, method: str, url: str, **kwargs: Any):
        self._validate_url(url)
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("allow_redirects", False)
        kwargs.setdefault("stream", True)
        last_error: CrawlerError | None = None

        for attempt in range(self.max_attempts):
            try:
                response = self.session.request(method, url, **kwargs)
            except requests.Timeout as exc:
                last_error = CrawlerError(
                    self.platform, "CRAWL_TIMEOUT", str(exc) or "request timed out", True
                )
            except requests.RequestException as exc:
                last_error = CrawlerError(
                    self.platform, "CRAWL_NETWORK_ERROR", str(exc), True
                )
            else:
                status = int(response.status_code)
                if 200 <= status < 300:
                    return response
                if 300 <= status < 400:
                    raise CrawlerError(
                        self.platform,
                        "CRAWL_REDIRECT_BLOCKED",
                        "redirect responses are not followed",
                        False,
                    )
                if status in {401, 403}:
                    message = f"request rejected with HTTP {status}"
                    try:
                        error_payload = json.loads(self._read_body(response).decode("utf-8-sig"))
                        detail = error_payload.get("detail", {}) if isinstance(error_payload, dict) else {}
                        if isinstance(detail, dict):
                            message = detail.get("message_zh") or detail.get("message") or message
                    except Exception:
                        pass
                    raise CrawlerError(
                        self.platform,
                        f"CRAWL_HTTP_{status}",
                        message,
                        False,
                    )
                retryable = status == 429 or status >= 500
                last_error = CrawlerError(
                    self.platform,
                    f"CRAWL_HTTP_{status}",
                    f"request failed with HTTP {status}",
                    retryable,
                )
                if not retryable:
                    raise last_error

            if attempt + 1 < self.max_attempts:
                self.sleep(2**attempt)

        if last_error is None:
            last_error = CrawlerError(
                self.platform, "CRAWL_UNKNOWN_ERROR", "request failed", False
            )
        raise last_error

    def _read_body(self, response) -> bytes:
        headers = getattr(response, "headers", {}) or {}
        content_length = headers.get("Content-Length") or headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_response_bytes:
                    raise CrawlerError(
                        self.platform,
                        "CRAWL_RESPONSE_TOO_LARGE",
                        "response exceeds configured size limit",
                        False,
                    )
            except ValueError:
                pass

        chunks: list[bytes] = []
        total = 0
        iterator = getattr(response, "iter_content", None)
        if callable(iterator):
            for chunk in iterator(chunk_size=8192):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self.max_response_bytes:
                    raise CrawlerError(
                        self.platform,
                        "CRAWL_RESPONSE_TOO_LARGE",
                        "response exceeds configured size limit",
                        False,
                    )
                chunks.append(chunk)
            return b"".join(chunks)

        body = getattr(response, "content", None)
        if body is None:
            body = str(getattr(response, "text", "")).encode("utf-8")
        if len(body) > self.max_response_bytes:
            raise CrawlerError(
                self.platform,
                "CRAWL_RESPONSE_TOO_LARGE",
                "response exceeds configured size limit",
                False,
            )
        return body

    def _validate_url(self, url: str) -> tuple[str, str]:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            raise CrawlerError(
                self.platform, "CRAWL_INVALID_URL", f"invalid crawl URL: {url}", False
            )
        if self.allowed_hosts and not any(
            host == allowed or host.endswith(f".{allowed}")
            for allowed in self.allowed_hosts
        ):
            raise CrawlerError(
                self.platform,
                "CRAWL_URL_NOT_ALLOWED",
                f"crawl URL host is not allowed: {host}",
                False,
            )
        try:
            addresses = self.resolver(host)
        except OSError as exc:
            raise CrawlerError(
                self.platform, "CRAWL_DNS_ERROR", str(exc), True
            ) from exc
        if not addresses:
            raise CrawlerError(
                self.platform, "CRAWL_DNS_ERROR", f"host did not resolve: {host}", True
            )
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise CrawlerError(
                    self.platform,
                    "CRAWL_PRIVATE_ADDRESS",
                    f"crawl target resolves to a non-public address: {address}",
                    False,
                )
        preferred = next((address for address in addresses if ":" not in address), addresses[0])
        return host, preferred
