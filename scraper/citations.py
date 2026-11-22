"""Шүүхийн шийдвэрийн текстээс хуулийн зүйл, заалтын ишлэлийг ялгах.

Жишээ:
    "Эрүүгийн хуулийн 17.1 дүгээр зүйлийн 1 дэх хэсэгт"
        -> {"law": "Эрүүгийн хууль", "article": "17.1", "part": "1", "provision": None}
    "Иргэний хуулийн 227 дугаар зүйлийн 227.1-д"
        -> {"law": "Иргэний хууль", "article": "227", "part": None, "provision": "227.1"}
    "ЗХШХШТХ-ийн 106.3.1-д"
        -> {"law": "Захиргааны хэрэг шүүхэд хянан шийдвэрлэх тухай хууль", "provision": "106.3.1"}

Зүйлийн дугаарлалт хуулиас хамаарч өөр байдаг (Эрүүгийн хуульд "17.1 дүгээр зүйл",
Иргэний хуульд "227.1" нь 227 дугаар зүйлийн заалт). Иймд "зүйл" гэж тодорхой
бичигдсэн дугаарыг article, бусад цэгтэй дугаарыг provision гэж хадгална.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

ABBREVIATIONS = {
    "ҮХ": "Монгол Улсын Үндсэн хууль",
    "ЭХ": "Эрүүгийн хууль",
    "ИХ": "Иргэний хууль",
    "ЗЕХ": "Захиргааны ерөнхий хууль",
    "ЗХ": "Зөрчлийн тухай хууль",
    "ЗТХ": "Зөрчлийн тухай хууль",
    "ЭХХШТХ": "Эрүүгийн хэрэг хянан шийдвэрлэх тухай хууль",
    "ИХШХШТХ": "Иргэний хэрэг шүүхэд хянан шийдвэрлэх тухай хууль",
    "ЗХШХШТХ": "Захиргааны хэрэг шүүхэд хянан шийдвэрлэх тухай хууль",
    "ЗХХШТХ": "Зөрчил шалган шийдвэрлэх тухай хууль",
    "ЗШШТХ": "Зөрчил шалган шийдвэрлэх тухай хууль",
    "ХТХ": "Хөдөлмөрийн тухай хууль",
    "ГБХ": "Гэр бүлийн тухай хууль",
}

UPPER = "А-ЯӨҮЁ"
LOWER = "а-яөүё"
SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹"

# "...хуулийн" гэж төгссөн бүтэн нэр эсвэл "ЭХХШТХ-ийн" гэх товчлол
LAW_WORD_RE = re.compile(rf"(?<![{UPPER}{LOWER}])хуул(?:ийн|иар|ьд)(?![{LOWER}])")
ABBR_RE = re.compile(rf"(?<![{UPPER}{LOWER}])(?P<abbr>[{UPPER}]{{2,8}})\s?-?\s?(?:ийн|ын|ний|ий|д|т)(?![{LOWER}])")

# Хуулийн нэрийн араас ирэх ишлэлийн гинж: тоо, "дүгээр зүйлийн", "1 дэх хэсэг", таслал, "болон"
_NUM = rf"\d+[{SUP}]*(?:\.\d+[{SUP}]*)*"
_SUFFIX = rf"(?:\s?-\s?[{LOWER}]+)?"
_WORD = rf"(?:дүгээр|дугаар|дэх|дахь|зүйл[{LOWER}]*|(?:хэсэг|хэсг)[{LOWER}]*|заалт[{LOWER}]*|болон|ба)"
# "Эрүүгийн хуулийн тусгай ангийн 11.6 дугаар зүйл"
PART_OF_CODE_RE = re.compile(r"\s*(?:ерөнхий|тусгай)\s+ангийн")
CHAIN_RE = re.compile(rf"(?:\s*(?:{_NUM}{_SUFFIX}|{_WORD}(?![{LOWER}])|,))+")
UNIT_RE = re.compile(
    rf"(?P<num>{_NUM}(?:{_SUFFIX})?(?:\s*,\s*{_NUM}(?:{_SUFFIX})?)*)"
    rf"(?:\s+(?:дүгээр|дугаар|дэх|дахь)\s+(?P<what>зүйл|хэсэг|хэсг|заалт))?"
)

MAX_NAME_WORDS = 10


@dataclass
class Citation:
    law: str
    article: str | None = None
    part: str | None = None
    provision: str | None = None
    text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _law_name_before(text: str, end: int) -> tuple[str, int] | None:
    """`end` байрлалд "хуулийн" эхэлж байхад түүний өмнөх нэрийг олно.

    Том үсгээр эхэлсэн үг хүртэл буцаж уншина ("... Захиргааны хэрэг шүүхэд хянан
    шийдвэрлэх тухай хуулийн").
    """
    words = list(re.finditer(rf"[{UPPER}{LOWER}]+", text[max(0, end - 200):end]))
    offset = max(0, end - 200)
    for w in reversed(words[-MAX_NAME_WORDS:]):
        between = text[offset + w.end():end]
        if re.search(r"[.;:!?()\n]", between):
            break
        if w.group()[0].isupper():
            start = offset + w.start()
            return text[start:end].strip(), start
    return None


def _parse_chain(law: str, chain: str) -> list[Citation]:
    out: list[Citation] = []
    current: Citation | None = None
    for m in UNIT_RE.finditer(chain):
        what = m.group("what")
        raw = m.group().strip()
        nums = re.findall(_NUM, m.group("num"))
        if what is None:
            # Таслалаар жагсаасан дугаар бүр бие даасан ишлэл
            for num in nums:
                if current is not None and current.article and current.provision is None and (
                        num.startswith(current.article + ".") or current.part is not None):
                    current.provision = num
                    current.text += " " + num
                else:
                    current = Citation(law=law, provision=num, text=num)
                    out.append(current)
        elif what == "заалт":
            if current is not None and current.provision is None:
                current.provision = nums[0]
                current.text += " " + raw
            else:
                current = Citation(law=law, article=current.article if current else None,
                                   part=current.part if current else None, provision=nums[0], text=raw)
                out.append(current)
        elif what == "зүйл":
            for num in nums:
                if current is not None and current.article and current.provision is None \
                        and current.part is None and num.startswith(current.article + "."):
                    # "123 дугаар зүйлийн 123.1, 75⁸ дугаар зүйл" -> 123.1 нь 123-ын заалт
                    current.provision = num
                    current.text += " " + num
                    continue
                current = Citation(law=law, article=num, text=raw)
                out.append(current)
        else:  # хэсэг
            article = current.article if current is not None else None
            if len(nums) == 1 and "." in nums[0] and current is not None and current.provision is None:
                # "67 дугаар зүйлийн 67.1 дэх хэсэг" -> заалтын бүтэн дугаар
                current.provision = nums[0]
                current.text += " " + raw
                continue
            for num in nums:
                if current is not None and current.part is None and current.provision is None:
                    current.part = num
                    current.text += " " + raw
                else:
                    current = Citation(law=law, article=article, part=num, text=raw)
                    out.append(current)
    return out


def _normalize_law(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"хуул(?:ийн|иар|ьд)$", "хууль", name)
    return name


def extract_citations(text: str) -> list[Citation]:
    """Текстэд дурдагдсан хуулийн зүйл, хэсэг, заалтуудыг дарааллаар нь буцаана."""
    found: list[tuple[int, list[Citation]]] = []
    for m in LAW_WORD_RE.finditer(text):
        name = _law_name_before(text, m.start())
        if name is None:
            continue
        pos = m.end()
        part = PART_OF_CODE_RE.match(text, pos)
        if part:
            pos = part.end()
        chain = CHAIN_RE.match(text, pos)
        if not chain or not re.search(r"\d", chain.group()):
            continue
        law = _normalize_law(name[0] + " " + m.group())
        found.append((m.start(), _parse_chain(law, chain.group())))
    for m in ABBR_RE.finditer(text):
        abbr = m.group("abbr")
        if abbr not in ABBREVIATIONS:
            continue
        chain = CHAIN_RE.match(text, m.end())
        if not chain or not re.search(r"\d", chain.group()):
            continue
        found.append((m.start(), _parse_chain(ABBREVIATIONS[abbr], chain.group())))
    found.sort(key=lambda x: x[0])
    return [c for _, cs in found for c in cs]


def unique_citations(citations: list[Citation]) -> list[dict]:
    """Давхардсан ишлэлийг хасаж, хэдэн удаа дурдсаныг тоолно."""
    seen: dict[tuple, dict] = {}
    for c in citations:
        key = (c.law, c.article, c.part, c.provision)
        if key in seen:
            seen[key]["count"] += 1
        else:
            d = c.to_dict()
            d.pop("text")
            d["count"] = 1
            seen[key] = d
    return list(seen.values())
