"""legalinfo.mn-ээс хуулийн хуудсыг эелдэгээр татах.

Ашиглах:
    python -m scraper.legalinfo 16390263044601 --out data/laws
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .articles import split_articles

BASE = "https://legalinfo.mn"
USER_AGENT = "mongol-ai-huulch-research/0.1 (+https://github.com/zesee12345-prog/mongol-ai-huulch)"
MIN_INTERVAL = 1.0  # секундэд 1-ээс олон хүсэлт илгээхгүй


class PoliteSession:
    def __init__(self, min_interval: float = MIN_INTERVAL) -> None:
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.min_interval = min_interval
        self._last = 0.0

    def get(self, url: str, **kw) -> requests.Response:
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        for attempt in range(4):
            try:
                r = self.s.get(url, timeout=30, **kw)
                self._last = time.monotonic()
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** attempt * 5)
                    continue
                r.raise_for_status()
                return r
            except requests.ConnectionError:
                time.sleep(2 ** attempt * 5)
        raise RuntimeError(f"татаж чадсангүй: {url}")


def law_url(law_id: str) -> str:
    return f"{BASE}/mn/detail?lawId={law_id}"


def extract_text(html: str) -> tuple[str, str]:
    """HTML-ээс гарчиг ба хуулийн цэвэр текстийг гаргана."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title else ""
    main = soup.find("main") or soup.find(id="content") or soup.body or soup
    text = main.get_text("\n")
    lines = [l.strip() for l in text.splitlines()]
    return title, "\n".join(l for l in lines if l)


def parse_law(law_id: str, html: str) -> dict:
    title, text = extract_text(html)
    articles = split_articles(text)
    return {
        "law_id": law_id,
        "source_url": law_url(law_id),
        "title": title,
        "article_count": len(articles),
        "articles": [a.to_dict() for a in articles],
        "raw_text": text,
    }


def fetch_law(session: PoliteSession, law_id: str) -> dict:
    return parse_law(law_id, session.get(law_url(law_id)).text)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("law_ids", nargs="+")
    p.add_argument("--out", default="data/laws")
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sess = PoliteSession()
    for law_id in args.law_ids:
        law = fetch_law(sess, law_id)
        (out / f"{law_id}.json").write_text(json.dumps(law, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{law_id}: {law['article_count']} зүйл")


if __name__ == "__main__":
    main()
