from app.selenium_client import SeleniumClient
from app.parser import EquityParser
from app.csv_writer import CsvWriter
def main():
    selenium_client = SeleniumClient()
    selenium_client.open("https://finance.yahoo.com/research-hub/screener/equity/")
    html = selenium_client.get_page_source()
    parser = EquityParser()
    data = parser.parse(html)

    print(data)
    writer = CsvWriter()
    output = "equities.csv"
    writer.write(data, output)
    selenium_client.close()
if __name__ == "__main__":
    main()
