from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class SeleniumClient:
    def __init__(self, headless: bool = True):
        options = Options()
        if headless:
            options.add_argument("--headless=new")

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 10)

    def open(self, url: str):
        self.driver.get(url)

    def get_page_source(self) -> str:
        return self.driver.page_source

    def close(self):
        self.driver.quit()
