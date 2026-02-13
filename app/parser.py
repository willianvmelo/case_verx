from bs4 import BeautifulSoup

class EquityParser:
    def parse(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        rows = soup.select("table tbody tr")

        results = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue

            results.append({
                "symbol": cols[0].get_text(strip=True),
                "name": cols[1].get_text(strip=True),
                "price": cols[2].get_text(strip=True)
            })

        return results
