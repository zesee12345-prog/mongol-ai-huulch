"""Хуулийн текстийг бүлэг, зүйл, заалтаар хуваах."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

# Нэмэгдсэн зүйл, заалтын дугаар дээд индекстэй байж болно: 32¹, 1¹.1
SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹"
NUM = rf"\d+[{SUP}]*"

# "1 дүгээр зүйл", "2 дугаар зүйл", "32¹ дүгээр зүйл." гэх мэт
ARTICLE_RE = re.compile(
    rf"^\s*(?P<num>{NUM}(?:\s*/\d+)?)\s*(?:-?\s*(?:дүгээр|дугаар|ийн|ын))\s+зүйл\.?\s*(?P<title>.*)$",
    re.IGNORECASE,
)
CHAPTER_RE = re.compile(
    r"^\s*(?P<ord>[А-ЯӨҮЁа-яөүё]+|\d+)\s+(?:дүгээр|дугаар)?\s*бүлэг\s*$|^\s*[А-ЯӨҮЁ]+\s+БҮЛЭГ\s*$",
    re.IGNORECASE,
)
# "1.1.", "12.3.4.", "1¹.1." гэх мэт заалт
CLAUSE_RE = re.compile(rf"^\s*(?P<num>{NUM}(?:\.{NUM})+)\.?\s*(?P<text>[^\d\s{SUP}].*)$")


@dataclass
class Clause:
    number: str
    text: str


@dataclass
class Article:
    number: str
    title: str
    chapter: str | None
    text: str
    clauses: list[Clause] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def split_articles(text: str) -> list[Article]:
    """Хуулийн бүтэн текстийг зүйл бүрээр нь хуваана.

    Эхний зүйлээс өмнөх хэсгийг (гарчиг, огноо) алгасна.
    """
    articles: list[Article] = []
    chapter: str | None = None
    pending_chapter = False
    current: Article | None = None
    body: list[str] = []

    def flush() -> None:
        if current is None:
            return
        current.text = "\n".join(l for l in body if l.strip()).strip()
        current.clauses = _clauses(body)
        articles.append(current)

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if CHAPTER_RE.match(line):
            chapter = line
            pending_chapter = True
            continue
        if pending_chapter and not ARTICLE_RE.match(line):
            # Бүлгийн гарчиг ("НИЙТЛЭГ ҮНДЭСЛЭЛ")
            chapter = f"{chapter} {line}"
            pending_chapter = False
            continue
        pending_chapter = False
        m = ARTICLE_RE.match(line)
        if m:
            flush()
            current = Article(
                number=re.sub(r"\s+", "", m.group("num")),
                title=m.group("title").strip(),
                chapter=chapter,
                text="",
            )
            body = []
            continue
        if current is not None:
            body.append(line)
    flush()
    return articles


def _clauses(lines: list[str]) -> list[Clause]:
    out: list[Clause] = []
    for line in lines:
        m = CLAUSE_RE.match(line)
        if m:
            out.append(Clause(m.group("num"), m.group("text").strip()))
        elif out:
            out[-1].text += " " + line.strip()
    return out
