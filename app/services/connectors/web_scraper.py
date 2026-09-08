import asyncio
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

_MAX_REDIRECTS = 5
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


async def _validate_public_http_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) URLs are allowed.")
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not allowed.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("URL hostname could not be resolved.") from exc
    if not addresses:
        raise ValueError("URL hostname could not be resolved.")
    for address in addresses:
        ip = ipaddress.ip_address(str(address[4][0]).split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("Private, loopback, link-local, and reserved destinations are not allowed.")
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
    headers = {
        "User-Agent": "NexusAI-Bot/1.0 (+http://localhost:8501)",
    }
    current_url = await _validate_public_http_url(url)
    body = bytearray()
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False, trust_env=False) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            async with client.stream("GET", current_url, headers=headers) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise ValueError("Redirect response omitted its destination.")
                    current_url = await _validate_public_http_url(urljoin(current_url, location))
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
