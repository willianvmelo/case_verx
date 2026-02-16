import csv
from pathlib import Path

from app.csv_writer import CsvWriter


def read_csv(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_csv_writer_writes_header_and_rows(tmp_path: Path):
    path = tmp_path / "out.csv"
    data = [
        {"symbol": "AAPL", "name": "Apple Inc.", "price": "100"},
        {"symbol": "MSFT", "name": "Microsoft", "price": "200"},
    ]

    CsvWriter().write(data, str(path))

    rows = read_csv(path)
    assert rows == data


def test_csv_writer_writes_only_header_when_empty(tmp_path: Path):
    path = tmp_path / "out.csv"

    CsvWriter().write([], str(path))

    # DictReader em arquivo só com header retorna lista vazia
    rows = read_csv(path)
    assert rows == []

    # O arquivo precisa existir e ter o header correto
    content = path.read_text(encoding="utf-8").strip().splitlines()
    assert content[0] == "symbol,name,price"