from app.selenium_client import SeleniumClient

def main():
    selenium_client = SeleniumClient()
    selenium_client.open("https://finance.yahoo.com/research-hub/screener/equity/")
    print(selenium_client.driver.title)
    selenium_client.close()
if __name__ == "__main__":
    main()
