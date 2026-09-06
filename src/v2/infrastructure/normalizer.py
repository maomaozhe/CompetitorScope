"""Deterministic HTML/plain-text normalization."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from src.v2.ports import FetchedResource, NormalizedResource


_BLOCK_TAGS = {
    "article",
    "br",
    "div",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "p",
    "section",
    "td",
    "th",
    "tr",
}
_IGNORED_TAGS = {"script", "style", "noscript", "svg"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in _IGNORED_TAGS:
            self.ignored_depth += 1
        elif tag in _BLOCK_TAGS and self.ignored_depth == 0:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORED_TAGS and self.ignored_depth:
            self.ignored_depth -= 1
        elif tag in _BLOCK_TAGS and self.ignored_depth == 0:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.ignored_depth == 0:
            self.parts.append(data)


def _clean_text(value: str) -> str:
    lines = []
    for raw_line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[\t\f\v ]+", " ", raw_line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


class DeterministicTextNormalizer:
    version = "deterministic-text.v1"

    def normalize(self, resource: FetchedResource) -> NormalizedResource:
        if resource.media_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
            raise ValueError(f"unsupported media type: {resource.media_type or 'unknown'}")
        decoded = resource.content.decode("utf-8", errors="replace")
        if resource.media_type in {"text/html", "application/xhtml+xml"}:
            parser = _TextExtractor()
            parser.feed(decoded)
            decoded = "".join(parser.parts)
        text = _clean_text(decoded)
        if not text:
            raise ValueError("normalized source is empty")
        return NormalizedResource(text=text, parser_version=self.version)
