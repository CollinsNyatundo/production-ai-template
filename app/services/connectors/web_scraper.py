import re
from html.parser import HTMLParser

import httpx


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
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()

    parser = SimpleTextExtractor()
    parser.feed(resp.text)
    extracted: str = str(parser.get_text())

    if not extracted:
        extracted = f"Web content from {url}"
    return extracted
