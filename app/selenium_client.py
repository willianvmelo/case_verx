from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

class SeleniumClient:
    def __init__(self, headless: bool = True):
        options = Options()

        if headless:
            options.add_argument("--headless=new")

        # ESSENCIAIS para WSL / containers / servidores
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        # Evita problemas gráficos
        options.add_argument("--disable-gpu")

        # Tamanho da janela (alguns sites dependem disso)
        options.add_argument("--window-size=1920,1080")

        # Opcional: evita detecção simples de automação
        options.add_argument("--disable-blink-features=AutomationControlled")

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 10)

    def open(self, url: str):
        self.driver.get(url)

    def get_page_source(self) -> str:
        return self.driver.page_source

    def close(self):
        self.driver.quit()
