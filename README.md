# Монгол AI хуульч

Монгол Улсын хууль тогтоомж, шүүхийн шийдвэр дээр суурилсан, ишлэлтэй хариулт өгдөг RAG систем.

## Одоогийн шат: legalinfo.mn татагч (туршилт)

```bash
pip install -r requirements.txt
python -m pytest
python -m scraper.legalinfo 16390263044601 --out data/laws
```

Гаралт нь `data/laws/<lawId>.json` бөгөөд хуулийг бүлэг, зүйл, заалтаар хуваасан байна.

Дүрэм: секундэд 1-ээс олон хүсэлт илгээхгүй, User-Agent-д төслийн нэрийг бичнэ, татсан өгөгдлийг repository-д commit хийхгүй.
