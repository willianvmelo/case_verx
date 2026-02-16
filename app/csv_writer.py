import csv
import os
from typing import Iterable


class CsvWriter:
    FIELDNAMES = ["symbol", "name", "price"]

    def write(self, data: list[dict], path: str):
        """
        Compatibilidade com versão antiga:
        escreve tudo de uma vez.
        """
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writeheader()
            writer.writerows(data)

    # ⭐ NOVO: modo streaming
    def write_rows(self, rows: Iterable[dict], path: str):
        """
        Escreve incrementalmente (append).
        Cria header apenas se arquivo não existir.
        Ideal para crawlers grandes.
        """
        file_exists = os.path.exists(path)

        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)

            if not file_exists:
                writer.writeheader()

            for row in rows:
                writer.writerow(row)
