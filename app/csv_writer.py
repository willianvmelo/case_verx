import csv

class CsvWriter:
    def write(self, data: list[dict], path: str):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["symbol", "name", "price"]
            )
            writer.writeheader()
            writer.writerows(data)
