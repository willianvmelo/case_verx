from app.selenium_client import SeleniumClient
from app.parser import EquityParser
from app.csv_writer import CsvWriter
from app.pages.yahoo_screener_page import YahooScreenerPage


class CrawlerService:
    def __init__(self):
        self.client = SeleniumClient()
        self.parser = EquityParser()
        self.writer = CsvWriter()

    def run(self, region: str, output: str) -> int:
        try:
            page = YahooScreenerPage(self.client, debug=True)
            page.open()
            page.apply_region(region)

            seen = set()
            total = 0

            for table_html in page.iter_pages_table_html():
                rows = self.parser.parse(table_html)

                new_rows = []

                for r in rows:
                    key = (r.get("symbol") or "").strip()

                    if key and key not in seen:
                        seen.add(key)
                        new_rows.append(r)

                if new_rows:
                    self.writer.write_rows(new_rows, output)
                    total += len(new_rows)

            return total

        finally:
            self.client.close()
