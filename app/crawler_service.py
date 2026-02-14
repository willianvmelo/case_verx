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
            page = YahooScreenerPage(self.client)
            page.open()
            page.apply_region(region)

            all_rows = []
            seen = set()

            for html in page.iter_pages_html():
                rows = self.parser.parse(html)
                for r in rows:
                    key = r.get("symbol")
                    if key and key not in seen:
                        seen.add(key)
                        all_rows.append(r)

            self.writer.write(all_rows, output)
            return len(all_rows)

        finally:
            self.client.close()
