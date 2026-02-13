from app.selenium_client import SeleniumClient
from app.parser import EquityParser
from app.csv_writer import CsvWriter

class CrawlerService:
    def __init__(self):
        self.browser = SeleniumClient()
        self.parser = EquityParser()
        self.writer = CsvWriter()

    def run(self, region: str, output: str):
        url = "https://finance.yahoo.com/screener/equity/new"
        self.browser.open(url)

        # Aqui entra a lógica do filtro de região + paginação
        html = self.browser.get_page_source()
        data = self.parser.parse(html)

        self.writer.write(data, output)
        self.browser.close()

        return len(data)
