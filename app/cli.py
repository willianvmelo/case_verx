from app.selenium_client import SeleniumClient
from app.parser import EquityParser

def main():
    selenium_client = SeleniumClient()
    selenium_client.open("https://finance.yahoo.com/research-hub/screener/equity/")
    html = selenium_client.get_page_source()
    parser = EquityParser() 
    print(parser.parse(html))
    selenium_client.close()
if __name__ == "__main__":
    main()
