import json
from datetime import date
from pathlib import Path

import pytest

from scraper.anonymize import anonymize
from scraper.citations import extract_citations
from scraper.shuukh import (
    ListRow, RobotsDisallowed, ShuukhClient, crawl, list_url, parse_decision, parse_list, split_sections,
)

FIX = Path(__file__).parent / "fixtures" / "shuukh"


def load(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def cites(rec):
    return {(c["law"], c["article"], c["part"], c["provision"]) for c in rec["citations"]}


# ------------------------------------------------------------------ жагсаалт

def test_parse_list_administrative():
    rows, count = parse_list(load("list_administrative_1.json"))
    assert count == 1765
    assert [r.decision_id for r in rows] == [21861, 21870]
    r = rows[0]
    assert (r.court_cat, r.court_type) == (3, 1)
    assert r.court == "Говь-Алтай аймаг дахь Захиргааны хэргийн анхан шатны шүүх"
    assert r.date == "2026-11-18"
    assert r.number == "112/ШШ2026/0048"
    assert r.judge == "Шүрэнцэцэгийн Энхцэцэг"
    assert r.categories == ["Бусад"]
    assert r.has_appeal_decision is False
    assert rows[1].has_appeal_decision is True  # "Магадлал гарсан"
    assert " " not in r.url and r.url.startswith("https://shuukh.mn/single_case/21861?")


def test_parse_list_criminal_page2_soft_hyphen_and_articles():
    rows, count = parse_list(load("list_criminal_2.json"))
    assert count == 6872
    assert rows[0].categories == ["12.1.2.1", "12.1.2.3", "12.1.3"]
    assert rows[1].number == "2025/ШЦТ/118"  # U+00AD хассан


def test_list_url_has_required_params():
    url = list_url(2, 1, 3, date(2026, 1, 1), date(2026, 11, 22))
    assert "court_order=1" in url and "date_order=1" in url and "page=3" in url
    assert "judge" not in url  # judge= параметр 500 алдаа өгдөг
    assert "daterange=2026%2F01%2F01%20-%202026%2F11%2F22%20" in url


# ------------------------------------------------------------------ шийдвэр

def test_parse_criminal_decision():
    rec = parse_decision(load("decision_criminal_1.html"), 131897, 2)
    assert rec["key"] == "criminal/131897"
    assert rec["level"] == "first_instance"
    assert rec["decision_type"] == "Шийтгэх тогтоол"
    assert rec["court"] == "Төв аймаг дахь сум дундын анхан шатны шүүх /Эрүүгийн хэрэг/"
    assert rec["date"] == "2026-11-20"  # текст дэх "2025 11 20"-ыг биш metadata-г авна
    assert rec["number"] == "2025/ШЦТ/529"
    assert rec["case_index"] == "317/2025/0483/Э"
    assert rec["judges"] == ["Цэдэвийн Отгонжаргал"]
    assert rec["prosecutor"] == "Э.Уянга"
    assert rec["charged_articles"] == ["11.6.1"]
    # "Эрүүгийн хуулийн тусгай ангийн 11.6 дугаар зүйлийн 1 дэх хэсэг" өөр өөр span-д хуваагдсан
    assert ("Эрүүгийн хууль", "11.6", "1", None) in cites(rec)
    assert ("Эрүүгийн хэрэг хянан шийдвэрлэх тухай хууль", "16.2", None, None) in cites(rec)
    assert rec["text"].splitlines()[1] == "МОНГОЛ УЛСЫН НЭРИЙН ӨМНӨӨС"
    assert "descriptive" in rec["sections"]
    # Шүүгч, нарийн бичгийн дарга, прокурорын нэр нийтийн мэдээлэл тул үлдэнэ
    for name in ("Ц.Отгонжаргал", "Б.Батмандал", "Э.Уянга", "Ж.Ануужинд"):
        assert name in rec["text"]


def test_parse_criminal_court_prefix_and_signature():
    rec = parse_decision(load("decision_criminal_2.html"), 130210, 2)
    assert rec["court_raw"].startswith("2025 - ")
    assert rec["court"] == "Баянзүрх, Сүхбаатар, Чингэлтэй дүүргийн Эрүүгийн хэргийн анхан шатны тойргийн шүүх"
    assert rec["prosecutor"] == "Б.Энх-Амгалан"
    assert "Б.Энх-Амгалан" in rec["text"]
    assert ("Эрүүгийн хууль", "91", None, "91.2.2") in cites(rec)
    assert ("Эрүүгийн хууль", "5.4", "4", None) in cites(rec)
    assert rec["text"].rstrip().endswith("ДАРГАЛАГЧ, ШҮҮГЧ Г.ХАТАНЦЭЦЭГ")


def test_parse_civil_decision_sections_superscript_and_phone_leak():
    rec = parse_decision(load("decision_civil_2.html"), 247160, 1)
    assert rec["category"] == "civil"
    assert rec["decision_type"] == "Шийдвэр"
    assert rec["dispute_types"] == ["Барьцаалан зээлдүүлэх байгууллагын зээл"]
    assert list(rec["sections"]) == ["intro", "descriptive", "reasoning", "operative"]
    assert rec["sections"]["operative"].startswith("1.Нэхэмжлэгч")
    law = "Иргэний хэрэг шүүхэд хянан шийдвэрлэх тухай хууль"
    assert (law, "75⁸", None, "75⁸.1") in cites(rec)  # <sup>8</sup> -> ⁸
    assert (law, "123", None, "123.1") in cites(rec)
    # Сайт дээр нууцлагдаагүй үлдсэн утасны дугаарыг бид нууцална
    assert "89110000" not in rec["text"] and "[УТАС]" in rec["text"]
    assert rec["anonymization"]["replaced"]["phone"] == 1
    assert "raw_text" not in rec


def test_parse_civil_word_junk_is_removed():
    rec = parse_decision(load("decision_civil_3.html"), 262938, 1, keep_raw=True)
    for junk in ("User", "Normal", "2026-11-03T14:09:00Z", "MsoNormalTable", "LsdException", "mso-"):
        assert junk not in rec["raw_text"]
    assert rec["judges"] == ["Л.Батжаргал"]
    assert "Л.Батжаргал" in rec["text"]
    assert "Хэргийн материалыг шүүх хянаад" in rec["sections"]["descriptive"]


def test_parse_administrative_decision():
    rec = parse_decision(load("decision_administrative_1.html"), 21861, 3)
    assert rec["decision_type"] == "Шүүгчийн захирамж"
    assert rec["case_index"].endswith("/З")
    assert ("Зөрчлийн тухай хууль", "11.18", "1", "1.25") in cites(rec)
    assert ("Захиргааны хэрэг шүүхэд хянан шийдвэрлэх тухай хууль", "67", None, "67.1") in cites(rec)
    assert "Ш.Энхцэцэг" in rec["text"]


# ------------------------------------------------------------------ туслах модулиуд

def test_split_sections():
    s = split_sections("Танилцуулга\nТОДОРХОЙЛОХ нь:\nА\nҮНДЭСЛЭХ нь:\nБ\nудирдлага болгон ТОГТООХ нь:\nВ")
    assert s == {"intro": "Танилцуулга", "descriptive": "А", "reasoning": "Б\nудирдлага болгон", "operative": "В"}


def test_anonymize_party_details():
    text = ("Шүүгч Д.Энхтөр даргалж, нэхэмжлэгч Б.Батболд (РД: УБ90010112, утас 9911-2233, "
            "bat@example.mn) хариуцагч Ц. Сарантуяа нарын хооронд. Б.Батболд нь Баянгол дүүргийн "
            "20 дугаар хороо, 15 дугаар байрны 34 тоотод оршин суух. 1234 УБА дугаартай машин. "
            "Данс 5012345678. 5,000,000 төгрөг. Эрүүгийн хуулийн 11.6 дугаар зүйл.")
    out, counts = anonymize(text)
    assert "Д.Энхтөр" in out  # албан тушаалтан
    assert out.count("[ИРГЭН-1]") == 2 and "[ИРГЭН-2]" in out  # нэг хүн = нэг орлуулагч
    for secret in ("Батболд", "Сарантуяа", "УБ90010112", "9911-2233", "bat@example.mn", "34 тоот",
                   "1234 УБА", "5012345678"):
        assert secret not in out
    assert "5,000,000 төгрөг" in out and "11.6 дугаар зүйл" in out
    assert counts["person"] == 3


def test_citations_abbreviation():
    cs = extract_citations("ЭХХШТХ-ийн 36.3 дугаар зүйлийн 1, 2 дахь хэсэг")
    assert [(c.law, c.article, c.part) for c in cs] == [
        ("Эрүүгийн хэрэг хянан шийдвэрлэх тухай хууль", "36.3", "1"),
        ("Эрүүгийн хэрэг хянан шийдвэрлэх тухай хууль", "36.3", "2"),
    ]


# ------------------------------------------------------------------ татагч (сүлжээгүй)

class FakeResponse:
    def __init__(self, text: str, status: int = 200):
        self.text, self.status_code, self.encoding = text, status, "utf-8"


class FakeHTTP:
    def __init__(self, routes: dict[str, str], robots: str = ""):
        import requests
        self.s = requests.Session()
        self.routes, self.robots, self.calls = routes, robots, []

    def get(self, url, **kw):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FakeResponse(self.robots)
        for prefix, body in self.routes.items():
            if prefix in url:
                return FakeResponse(body)
        return FakeResponse("<html></html>")


def test_crawl_saves_and_resumes(tmp_path):
    routes = {
        "/site/case_ajax": load("list_administrative_1.json"),
        "/single_case/": load("decision_administrative_1.html"),
    }
    http = FakeHTTP(routes)
    client = ShuukhClient(session=http)
    n = crawl(client, 3, 1, date(2026, 1, 1), date(2026, 11, 22), tmp_path, max_pages=1)
    assert n == 2
    saved = json.loads((tmp_path / "administrative" / "first_instance" / "21861.json").read_text("utf-8"))
    assert saved["decision_type"] == "Шүүгчийн захирамж"
    assert saved["listing"]["has_appeal_decision"] is False
    assert http.s.cookies.get("lang") == "mn"
    # Дахин ажиллуулахад аль хэдийн хадгалсан шийдвэрийг дахин татахгүй
    before = sum("/single_case/" in u for u in http.calls)
    assert crawl(client, 3, 1, date(2026, 1, 1), date(2026, 11, 22), tmp_path, max_pages=1) == 0
    assert sum("/single_case/" in u for u in http.calls) == before


def test_robots_disallow_is_respected(tmp_path):
    http = FakeHTTP({}, robots="User-agent: *\nDisallow: /site/\n")
    client = ShuukhClient(session=http)
    with pytest.raises(RobotsDisallowed):
        client.list_page(3, 1, 1, date(2026, 1, 1), date(2026, 1, 2))
    assert not any("/site/case_ajax" in u for u in http.calls)


def test_cloudflare_content_signals_robots_allows():
    robots = "# As a condition of accessing this website, you agree to abide by the following\n# content signals:\n"
    client = ShuukhClient(session=FakeHTTP({}, robots=robots))
    client.load_robots()
    assert client.robots.can_fetch("mongol-ai-huulch-research/0.1", "https://shuukh.mn/single_case/1")
