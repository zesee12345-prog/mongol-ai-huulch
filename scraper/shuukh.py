"""shuukh.mn (Шүүхийн шийдвэрийн цахим сан)-аас шүүхийн шийдвэрийг эелдэгээр татах.

Ашиглах:
    python -m scraper.shuukh --category criminal --level 1 \
        --from 2026-11-01 --to 2026-11-22 --max-pages 2 --out data/decisions

Сайтын бүтэц (2026-11 сард шалгасан):
  * Жагсаалт: GET /site/case_ajax?id={шат}&court_cat={ангилал}&page={n}&daterange=...
    -> JSON {"view": "<tr>...</tr>", "pagination_link": "...", "count": N}, хуудсанд 10 мөр.
    court_order, date_order-ыг "1" гэж заавал өгнө ("undefined" бол сервер 500 буцаана).
  * Шийдвэр: GET /single_case/{id}?...&court_cat={ангилал} — id нь ангилал бүрт тусдаа
    дугаарлагддаг тул (court_cat, id)-аар ялгана.
  * Шийдвэрийн текст хуудсан дээрээ HTML (Word-оос хуулсан) хэлбэрээр байна.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from datetime import date
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse, parse_qs
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, Comment

from .anonymize import Anonymizer
from .citations import extract_citations, unique_citations
from .legalinfo import PoliteSession, USER_AGENT, SUPERSCRIPT

BASE = "https://shuukh.mn"

CATEGORIES = {1: "civil", 2: "criminal", 3: "administrative"}
CATEGORY_IDS = {v: k for k, v in CATEGORIES.items()}
LEVELS = {1: "first_instance", 2: "appeal", 3: "supreme"}
LEVEL_IDS = {v: k for k, v in LEVELS.items()}

# Шийдвэрийн хэсгүүдийн гарчиг
SECTION_RE = re.compile(r"(ТОДОРХОЙЛОХ|ҮНДЭСЛЭХ|ТОГТООХ|ШИЙДВЭРЛЭХ|ЗАХИРАМЖЛАХ)\s+нь\s*:")
SECTION_NAMES = {
    "ТОДОРХОЙЛОХ": "descriptive",
    "ҮНДЭСЛЭХ": "reasoning",
    "ТОГТООХ": "operative",
    "ШИЙДВЭРЛЭХ": "operative",
    "ЗАХИРАМЖЛАХ": "operative",
}
DECISION_TYPES = [
    "Шийтгэх тогтоол", "Цагаатгах тогтоол", "Шүүгчийн захирамж", "Шүүхийн захирамж",
    "Магадлал", "Хяналтын шатны шүүхийн тогтоол", "Тогтоол", "Шийдвэр",
]
METADATA_KEYS = {
    "Шүүх": "court",
    "Шүүгч": "judges",
    "Хэргийн индекс": "case_index",
    "Дугаар": "number",
    "Огноо": "date",
    "Маргааны төрөл": "dispute_types",
    "Зүйл хэсэг": "charged_articles",
    "Улсын яллагч": "prosecutor",
}


# --------------------------------------------------------------------------- жагсаалт

@dataclass
class ListRow:
    decision_id: int
    court_cat: int
    court_type: int
    court: str
    date: str
    number: str
    judge: str
    categories: list[str]
    has_appeal_decision: bool
    has_supreme_decision: bool
    url: str


def _clean(s: str) -> str:
    s = s.replace("­", "").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()


def _split_list(s: str) -> list[str]:
    return [x for x in (_clean(p).rstrip(".") for p in re.split(r"[,\n]", s)) if x]


def parse_list(payload: str | dict) -> tuple[list[ListRow], int]:
    """/site/case_ajax-ийн JSON хариуг мөр бүрээр задлана. (мөрүүд, нийт тоо)"""
    data = json.loads(payload) if isinstance(payload, str) else payload
    soup = BeautifulSoup("<table>" + (data.get("view") or "") + "</table>", "html.parser")
    rows: list[ListRow] = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        link = tr.find("a", href=re.compile(r"/single_case/\d+"))
        if len(tds) < 7 or link is None:
            continue
        href = link["href"]
        m = re.search(r"/single_case/(\d+)", href)
        qs = parse_qs(urlparse(href).query)
        flags = [
            "гарсан" in (i.get("title") or "") and "гараагүй" not in (i.get("title") or "")
            for i in (tds[3].find("i"), tds[4].find("i")) if i is not None
        ] + [False, False]
        rows.append(ListRow(
            decision_id=int(m.group(1)),
            court_cat=int(qs.get("court_cat", ["0"])[0]),
            court_type=int(qs.get("id", ["0"])[0]),
            court=_clean(tds[0].get_text()),
            date=_clean(tds[1].get_text()),
            number=_clean(tds[2].get_text()),
            judge=_clean(tds[5].get_text()),
            categories=_split_list(tds[6].get_text()),
            has_appeal_decision=flags[0],
            has_supreme_decision=flags[1],
            url=urljoin(BASE, quote(href, safe="/?&=%:")),
        ))
    return rows, int(data.get("count") or 0)


# --------------------------------------------------------------------------- шийдвэр

def _metadata(soup: BeautifulSoup) -> dict:
    meta: dict = {}
    table = soup.select_one("div.full-search table.table-bordered") or soup.select_one("table.table-bordered")
    if table is None:
        return meta
    for tr in table.find_all("tr"):
        th, td = tr.find("th"), tr.find("td")
        if th is None or td is None:
            continue
        key = METADATA_KEYS.get(_clean(th.get_text()))
        if key:
            meta[key] = td.get_text("\n")
    for key in ("dispute_types", "charged_articles"):
        if key in meta:
            meta[key] = _split_list(meta[key])
    if "judges" in meta:
        meta["judges"] = _split_list(meta["judges"])
    for key in ("court", "case_index", "number", "date", "prosecutor"):
        if key in meta:
            meta[key] = _clean(meta[key])
    return meta


def _court_name(raw: str) -> str:
    """"2025 - Баянзүрх ... шүүх" -> "Баянзүрх ... шүүх" (сайтын нэрийн өмнөх оны угтвар)."""
    return re.sub(r"^\d{4}\s*-\s*", "", raw).strip()


def _decision_type(heading: str) -> str | None:
    h = heading.lower()
    for t in DECISION_TYPES:
        if h.endswith(t.lower()):
            return t
    return None


def body_lines(undsen) -> list[str]:
    """`.undsen` доторх Word-оос хуулсан HTML-ийг мөрүүд болгоно."""
    for c in undsen.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()  # <!--[if gte mso 9]><xml>...</xml><![endif]--> зэрэг
    for tag in undsen.find_all(["script", "style", "xml"]):
        tag.decompose()
    for sup in undsen.find_all("sup"):
        raw = sup.get_text()
        trail = " " if raw != raw.rstrip() else ""
        sup.replace_with(_clean(raw).translate(SUPERSCRIPT) + trail)
    lines: list[str] = []
    blocks = [p for p in undsen.find_all(["p", "li", "h1", "h2", "h3", "h4"]) if p.find(["p", "li"]) is None]
    for p in blocks:
        line = _clean(p.get_text(""))
        if line:
            lines.append(line)
    if not lines:
        lines = [l for l in (_clean(x) for x in undsen.get_text("\n").splitlines()) if l]
    return lines


def split_sections(text: str) -> dict[str, str]:
    """"ТОДОРХОЙЛОХ нь:", "ҮНДЭСЛЭХ нь:", "ТОГТООХ/ШИЙДВЭРЛЭХ/ЗАХИРАМЖЛАХ нь:" гарчгаар хуваана."""
    sections: dict[str, str] = {}
    marks = list(SECTION_RE.finditer(text))
    start, name = 0, "intro"
    for m in marks:
        chunk = text[start:m.start()].strip()
        if chunk:
            sections[name] = (sections.get(name, "") + "\n" + chunk).strip()
        name, start = SECTION_NAMES[m.group(1)], m.end()
    tail = text[start:].strip()
    if tail:
        sections[name] = (sections.get(name, "") + "\n" + tail).strip()
    return sections


def _judge_short(full: str) -> str | None:
    """"Шүрэнцэцэгийн Энхцэцэг" -> "Ш.Энхцэцэг", "Л.Батжаргал" -> "Л.Батжаргал"."""
    full = _clean(full)
    if re.match(r"^[А-ЯӨҮЁ][а-яөүё]?\.\s?[А-ЯӨҮЁ]", full):
        return full.replace(". ", ".")
    parts = full.split()
    if len(parts) >= 2:
        return f"{parts[0][0]}.{parts[-1]}"
    return None


def parse_decision(html: str, decision_id: int, court_cat: int, court_type: int = 1,
                   source_url: str | None = None, keep_raw: bool = False) -> dict:
    """Шийдвэрийн хуудсыг JSON-д бэлэн dict болгоно. Текстийг үргэлж нууцалсан хэлбэрээр хадгална."""
    soup = BeautifulSoup(html.lstrip("﻿"), "html.parser")
    meta = _metadata(soup)
    heading_tag = soup.select_one("#printableArea .decisionfullimg p") or soup.select_one(".decisionfullimg p")
    heading = _clean(heading_tag.get_text()) if heading_tag else ""
    undsen = soup.select_one("#source-html #printableArea .undsen") or soup.select_one(".undsen")
    lines = body_lines(undsen) if undsen is not None else []
    raw_text = "\n".join(lines)

    officials = set()
    for j in meta.get("judges", []):
        s = _judge_short(j)
        if s:
            officials.add(s)
    if meta.get("prosecutor"):
        s = _judge_short(meta["prosecutor"])
        if s:
            officials.add(s)
    anon = Anonymizer(keep_names=set(officials))
    text = anon.anonymize(raw_text)

    citations = unique_citations(extract_citations(text))
    if court_cat == 2:
        # Эрүүгийн хэрэгт "Зүйл хэсэг" нь Эрүүгийн хуулийн (2015) зүйл.хэсэг.заалт
        for code in meta.get("charged_articles", []):
            m = re.match(r"^(\d+\.\d+)\.(\d+)(?:\.(\d+))?$", code)
            if m and not any(c["law"] == "Эрүүгийн хууль" and c["article"] == m.group(1)
                             and c["part"] == m.group(2) for c in citations):
                citations.append({"law": "Эрүүгийн хууль", "article": m.group(1), "part": m.group(2),
                                  "provision": None, "count": 0})

    court_raw = meta.get("court", "")
    record = {
        "source": "shuukh.mn",
        "key": f"{CATEGORIES.get(court_cat, court_cat)}/{decision_id}",
        "decision_id": decision_id,
        "court_cat": court_cat,
        "category": CATEGORIES.get(court_cat),
        "court_type": court_type,
        "level": LEVELS.get(court_type),
        "source_url": source_url or decision_url(decision_id, court_cat, court_type),
        "court": _court_name(court_raw),
        "court_raw": court_raw,
        "decision_type": _decision_type(heading),
        "heading": heading,
        "date": meta.get("date"),
        "number": meta.get("number"),
        "case_index": meta.get("case_index"),
        "judges": meta.get("judges", []),
        "prosecutor": meta.get("prosecutor"),
        "dispute_types": meta.get("dispute_types", []),
        "charged_articles": meta.get("charged_articles", []),
        "citations": citations,
        "sections": split_sections(text),
        "text": text,
        "anonymization": {"method": "rules-v1", "replaced": anon.counts},
    }
    if keep_raw:
        record["raw_text"] = raw_text
    return record


# --------------------------------------------------------------------------- татагч

def decision_url(decision_id: int, court_cat: int, court_type: int = 1) -> str:
    return f"{BASE}/single_case/{decision_id}?id={court_type}&court_cat={court_cat}&bb=1"


def list_url(court_cat: int, court_type: int, page: int, date_from: date, date_to: date) -> str:
    # Сайтын JS-тэй адил төгсгөлд нь зай үлдээнэ
    daterange = f"{date_from:%Y/%m/%d} - {date_to:%Y/%m/%d} "
    params = [
        ("id", court_type), ("court_cat", court_cat), ("bb", 1), ("page", page),
        ("daterange", daterange), ("keyword", ""), ("court", ""), ("index_number", ""),
        ("number", ""), ("is_active", ""), ("court_order", 1), ("date_order", 1), ("result", ""),
    ]
    return f"{BASE}/site/case_ajax?" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params)


class RobotsDisallowed(RuntimeError):
    pass


class ShuukhClient:
    def __init__(self, session: PoliteSession | None = None) -> None:
        self.http = session or PoliteSession()
        self.http.s.cookies.set("lang", "mn", domain="shuukh.mn")
        self.robots: RobotFileParser | None = None
        self._warm: set[tuple[int, int]] = set()

    def load_robots(self) -> None:
        rp = RobotFileParser()
        try:
            rp.parse(self.http.get(f"{BASE}/robots.txt").text.splitlines())
        except (RuntimeError, requests.HTTPError):
            rp.parse([])  # robots.txt олдохгүй бол хязгаарлалтгүй гэж үзнэ
        self.robots = rp

    def _check(self, url: str) -> None:
        if self.robots is None:
            self.load_robots()
        if not self.robots.can_fetch(USER_AGENT, url):
            raise RobotsDisallowed(url)

    def _warmup(self, court_cat: int, court_type: int) -> None:
        # ci_session / csrf cookie-г авахын тулд жагсаалтын хуудсыг нэг удаа нээнэ
        if (court_cat, court_type) in self._warm:
            return
        url = f"{BASE}/cases/{court_cat}/{court_type}"
        self._check(url)
        self.http.get(url)
        self._warm.add((court_cat, court_type))

    def list_page(self, court_cat: int, court_type: int, page: int,
                  date_from: date, date_to: date) -> tuple[list[ListRow], int]:
        self._warmup(court_cat, court_type)
        url = list_url(court_cat, court_type, page, date_from, date_to)
        self._check(url)
        r = self.http.get(url, headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{BASE}/cases/{court_cat}/{court_type}",
        })
        return parse_list(r.text)

    def fetch_decision(self, row: ListRow, keep_raw: bool = False) -> dict:
        url = row.url
        self._check(url)
        r = self.http.get(url, headers={"Referer": f"{BASE}/cases/{row.court_cat}/{row.court_type}"})
        r.encoding = "utf-8"
        rec = parse_decision(r.text, row.decision_id, row.court_cat, row.court_type,
                             source_url=url, keep_raw=keep_raw)
        rec["listing"] = {
            "has_appeal_decision": row.has_appeal_decision,
            "has_supreme_decision": row.has_supreme_decision,
        }
        return rec


def crawl(client: ShuukhClient, court_cat: int, court_type: int, date_from: date, date_to: date,
          out: Path, max_pages: int | None = None, keep_raw: bool = False) -> int:
    """Огнооны мужид хамаарах шийдвэрүүдийг татаж `out/<ангилал>/<шат>/<id>.json` болгон хадгална.

    Өмнө нь татсан файлыг алгасдаг тул тасалдсан бол дахин ажиллуулахад үргэлжилнэ.
    """
    folder = out / CATEGORIES[court_cat] / LEVELS[court_type]
    folder.mkdir(parents=True, exist_ok=True)
    saved, page, total = 0, 1, None
    while max_pages is None or page <= max_pages:
        rows, total = client.list_page(court_cat, court_type, page, date_from, date_to)
        if not rows:
            break
        for row in rows:
            path = folder / f"{row.decision_id}.json"
            if path.exists():
                continue
            rec = client.fetch_decision(row, keep_raw=keep_raw)
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            saved += 1
        print(f"{CATEGORIES[court_cat]}/{LEVELS[court_type]} хуудас {page} "
              f"({page * 10}/{total}), шинээр {saved}", file=sys.stderr)
        if page * 10 >= total:
            break
        page += 1
    return saved


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--category", choices=list(CATEGORY_IDS), required=True)
    p.add_argument("--level", type=int, choices=[1, 2, 3], default=1,
                   help="1=анхан, 2=давж заалдах, 3=хяналт")
    p.add_argument("--from", dest="date_from", type=date.fromisoformat, required=True)
    p.add_argument("--to", dest="date_to", type=date.fromisoformat, default=date.today())
    p.add_argument("--max-pages", type=int, default=None)
    p.add_argument("--out", default="data/decisions")
    p.add_argument("--keep-raw", action="store_true",
                   help="нууцлаагүй эх текстийг ч хадгалах (зөвхөн дотоод шалгалтад)")
    args = p.parse_args()
    n = crawl(ShuukhClient(), CATEGORY_IDS[args.category], args.level, args.date_from, args.date_to,
              Path(args.out), max_pages=args.max_pages, keep_raw=args.keep_raw)
    print(f"{n} шийдвэр хадгаллаа", file=sys.stderr)


if __name__ == "__main__":
    main()
