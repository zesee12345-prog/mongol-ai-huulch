"""Шүүхийн шийдвэрийн текст дэх хувийн мэдээллийг нууцлах.

Зарчим (Хувь хүний мэдээлэл хамгаалах тухай хууль, 2021):
  * Хэргийн оролцогч иргэдийн нэр, регистр, утас, и-мэйл, хаяг, тээврийн хэрэгслийн
    улсын дугаар, дансны дугаарыг орлуулагчаар солино.
  * Нэг хүн текстийн турш нэг орлуулагчтай байна ([ИРГЭН-1], [ИРГЭН-2] ...), тиймээс
    RAG-ийн хариулт "хэн юу хийсэн" гэдгийг алдахгүй.
  * Шүүгч, прокурор зэрэг албан тушаалтны нэр нь нийтийн мэдээлэл тул `keep_names`-д
    дамжуулсан нэрсийг нууцлахгүй.
  * Энэ нь дүрэмд суурилсан эхний шат. "Батын Болд" хэлбэрийн (эцэг/эхийн нэр + нэр)
    бүтэн нэр, байгууллагын нэр, газар зүйн нарийн хаягийг бүрэн барьж чадахгүй тул
    нийтэд гаргахаас өмнө NER загвар эсвэл гар шалгалт нэмэх шаардлагатай.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

UPPER = "А-ЯӨҮЁ"
LOWER = "а-яөүё"

# Регистрийн дугаар: 2 кирилл үсэг + 8 цифр (УБ90010112, "ИЕ 85041512")
REGISTER_RE = re.compile(rf"(?<![{UPPER}{LOWER}])[{UPPER}]{{2}}\s?\d{{8}}(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Монгол утасны дугаар: 8 оронтой, 6/7/8/9-өөр эхэлнэ ("9911-2233", "99112233")
PHONE_RE = re.compile(r"(?<![\d.,])[6-9]\d{3}[\s-]?\d{4}(?!\d|[.,]\d)")
# Тээврийн хэрэгслийн улсын дугаар: "1234 УБА", "12-34УНЕ"
PLATE_RE = re.compile(rf"(?<!\d)\d{{2}}-?\d{{2}}\s?[{UPPER}]{{3}}(?![{UPPER}{LOWER}])")
# Дансны дугаар: 9-16 оронтой цифр (огноо, мөнгөн дүнгээс ялгахын тулд зай, таслалгүй)
ACCOUNT_RE = re.compile(r"(?<![\d.,])\d{9,16}(?!\d|[.,]\d)")
# Хаягийн нарийн хэсэг: "15 дугаар байрны 34 тоот", "3-р байр 12 тоот"
ADDRESS_RE = re.compile(
    rf"\d+[{UPPER}{LOWER}]?(?:\s?-?\s?(?:р|дүгээр|дугаар))?\s+байр[{LOWER}]*(?:\s*,?\s*\d+\s*(?:-?р\s+)?(?:орц[{LOWER}]*\s*,?\s*\d+\s*)?тоот)?"
    rf"|\d+\s*тоот"
)
# Овгийн эхний үсэг + нэр: "Б.Батболд", "Б. Батболд", "Бат.Болд", "БА.Болд"
INITIAL_NAME_RE = re.compile(
    rf"(?<![{UPPER}{LOWER}.])(?P<initial>[{UPPER}](?:[{UPPER}]|[{LOWER}]{{1,3}})?)\.\s?(?P<name>[{UPPER}][{LOWER}]{{2,}})"
)

# Нэр шиг харагдах боловч нэр биш үгс (хуулийн товчлол, гарчиг)
NOT_NAMES = {"Улсын", "Монгол", "Хууль", "Шүүх", "Иргэний", "Эрүүгийн", "Захиргааны"}


@dataclass
class Anonymizer:
    keep_names: set[str] = field(default_factory=set)
    people: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def _person(self, name: str) -> str:
        if name not in self.people:
            self.people[name] = f"[ИРГЭН-{len(self.people) + 1}]"
        return self.people[name]

    def _count(self, kind: str) -> None:
        self.counts[kind] = self.counts.get(kind, 0) + 1

    def _keep(self, initial: str, name: str) -> bool:
        if name in NOT_NAMES:
            return True
        for kept in self.keep_names:
            if name in kept and (kept.startswith(initial) or initial[0] in kept.split(name)[0]):
                return True
        return False

    def anonymize(self, text: str) -> str:
        def sub(kind: str, rx: re.Pattern, repl: str):
            nonlocal text

            def f(m: re.Match) -> str:
                self._count(kind)
                return repl
            text = rx.sub(f, text)

        sub("email", EMAIL_RE, "[И-МЭЙЛ]")
        sub("register", REGISTER_RE, "[РД]")
        sub("plate", PLATE_RE, "[УЛСЫН ДУГААР]")
        sub("account", ACCOUNT_RE, "[ДАНС]")
        sub("phone", PHONE_RE, "[УТАС]")
        sub("address", ADDRESS_RE, "[ХАЯГ]")

        def person(m: re.Match) -> str:
            initial, name = m.group("initial"), m.group("name")
            if self._keep(initial, name):
                return m.group()
            self._count("person")
            # Овог нь өөр байсан ч ижил нэртэй бол нэг хүн гэж үзэхгүй
            return self._person(f"{initial[0]}.{name}")
        text = INITIAL_NAME_RE.sub(person, text)
        return text


def anonymize(text: str, keep_names: set[str] | None = None) -> tuple[str, dict[str, int]]:
    a = Anonymizer(keep_names=set(keep_names or ()))
    return a.anonymize(text), a.counts
