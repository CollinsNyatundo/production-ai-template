import asyncio
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

_MAX_REDIRECTS = 5
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


async def _resolve_public_http_target(url: str) -> tuple[str, str, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) URLs are allowed.")
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not allowed.")

    try:
        explicit_port = parsed.port
    except ValueError as exc:
        raise ValueError("URL contains an invalid port.") from exc
    port = explicit_port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("URL hostname could not be resolved.") from exc
    if not addresses:
        raise ValueError("URL hostname could not be resolved.")
    resolved_ips = []
    for address in addresses:
        ip = ipaddress.ip_address(str(address[4][0]).split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("Private, loopback, link-local, and reserved destinations are not allowed.")
        resolved_ips.append(ip)

    selected_ip = resolved_ips[0]
    ip_host = f"[{selected_ip}]" if selected_ip.version == 6 else str(selected_ip)
    pinned_netloc = f"{ip_host}:{explicit_port}" if explicit_port is not None else ip_host

    original_host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    host_header = f"{original_host}:{explicit_port}" if explicit_port is not None else original_host
    request_url = urlunsplit((parsed.scheme, pinned_netloc, parsed.path, parsed.query, ""))
    return request_url, host_header, parsed.hostname


async def _validate_public_http_url(url: str) -> str:
    await _resolve_public_http_target(url)
    return url


class SimpleTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.ignore = False

    def handle_starttag(self, tag, attrs):
        if tag in ["script", "style", "head", "meta", "noscript"]:
            self.ignore = True

    def handle_endtag(self, tag):
        if tag in ["script", "style", "head", "meta", "noscript"]:
            self.ignore = False
        elif tag in ["p", "h1", "h2", "h3", "h4", "li", "div", "section"]:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if not self.ignore:
            cleaned = data.strip()
            if cleaned:
                self.text_parts.append(cleaned + " ")

    def get_text(self) -> str:
        full_text = "".join(self.text_parts)
        return str(re.sub(r"\n\s*\n", "\n\n", full_text).strip())


async def scrape_web_url(url: str) -> str:
    base_headers = {
        "User-Agent": "NexusAI-Bot/1.0 (+http://localhost:8501)",
    }
    current_url = url
    body = bytearray()
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False, trust_env=False) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            request_url, host_header, sni_hostname = await _resolve_public_http_target(current_url)
            request_headers = {**base_headers, "Host": host_header}
            extensions = {"sni_hostname": sni_hostname} if current_url.startswith("https://") else {}
            async with client.stream(
                "GET",
                request_url,
                headers=request_headers,
                extensions=extensions,
            ) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise ValueError("Redirect response omitted its destination.")
                    current_url = urljoin(current_url, location)
                    continue
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > _MAX_RESPONSE_BYTES:
                        raise ValueError("Web response exceeds the 2 MiB limit.")
                break
        else:
            raise ValueError("Too many redirects.")

    parser = SimpleTextExtractor()
    parser.feed(body.decode("utf-8", errors="replace"))
    extracted: str = str(parser.get_text())

    if not extracted:
        extracted = f"Web content from {url}"
    return extracted
