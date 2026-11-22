from scraper.articles import split_articles
from scraper.legalinfo import parse_law

SAMPLE = """
МОНГОЛ УЛСЫН ХУУЛЬ
2021 оны 12 дугаар сарын 17-ны өдөр
НЭГДҮГЭЭР БҮЛЭГ
НИЙТЛЭГ ҮНДЭСЛЭЛ
1 дүгээр зүйл.Хуулийн зорилт
1.1.Энэ хуулийн зорилт нь иргэний мэдээлэл хайх,
олж авах эрхийг хангахад оршино.
2 дугаар зүйл.Хууль тогтоомж
2.1.Энэ хуулийн тогтоомж нь Үндсэн хууль болон бусад хуулиас бүрдэнэ.
2.2.Олон улсын гэрээнд өөрөөр заасан бол гэрээний заалтыг дагаж мөрдөнө.
ХОЁРДУГААР БҮЛЭГ
МЭДЭЭЛЛИЙН ИЛ ТОД БАЙДАЛ
3 дугаар зүйл.Нэр томьёоны тодорхойлолт
3.1.Энэ хуульд хэрэглэсэн нэр томьёог дараах утгаар ойлгоно:
3.1.1.\"нийтийн мэдээлэл\" гэж ...;
"""


def test_split_articles():
    arts = split_articles(SAMPLE)
    assert [a.number for a in arts] == ["1", "2", "3"]
    assert arts[0].title == "Хуулийн зорилт"
    assert arts[0].chapter == "НЭГДҮГЭЭР БҮЛЭГ НИЙТЛЭГ ҮНДЭСЛЭЛ"
    assert arts[2].chapter == "ХОЁРДУГААР БҮЛЭГ МЭДЭЭЛЛИЙН ИЛ ТОД БАЙДАЛ"
    assert [c.number for c in arts[1].clauses] == ["2.1", "2.2"]
    assert "олж авах" in arts[0].clauses[0].text
    assert [c.number for c in arts[2].clauses] == ["3.1", "3.1.1"]


def test_parse_law_from_html():
    html = "<html><head><title>Туршилт</title><script>x</script></head><body><main>" + \
        "".join(f"<p>{l}</p>" for l in SAMPLE.strip().splitlines()) + "</main></body></html>"
    law = parse_law("123", html)
    assert law["title"] == "Туршилт"
    assert law["article_count"] == 3
    assert law["source_url"].endswith("lawId=123")
