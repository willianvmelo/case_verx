import app.crawler_service as crawler_module


class FakeClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakePage:
    def __init__(self, client, debug=True):
        self.client = client
        self.open_called = False
        self.apply_region_called_with = None

    def open(self):
        self.open_called = True

    def apply_region(self, region: str):
        self.apply_region_called_with = region

    def iter_pages_html(self):
        # O HTML não precisa ser real, porque o parser vai ser mockado
        yield "<html>page1</html>"
        yield "<html>page2</html>"

    # Compat com o crawler novo (que chama iter_pages_table_html)
    def iter_pages_table_html(self):
        # Reaproveita o mesmo gerador
        yield from self.iter_pages_html()


class FakeParser:
    def __init__(self):
        self.calls = []

    def parse(self, html: str):
        self.calls.append(html)
        if "page1" in html:
            return [
                {"symbol": "AAA", "name": "A", "price": "1"},
                {"symbol": "BBB", "name": "B", "price": "2"},
            ]
        return [
            {"symbol": "BBB", "name": "B", "price": "2"},  # duplicado
            {"symbol": "CCC", "name": "C", "price": "3"},
        ]


class FakeWriter:
    """
    Writer fake compatível com o crawler incremental (write_rows).
    Acumula tudo em .written para manter os asserts simples.
    """
    def __init__(self):
        self.written = []
        self.path = None
        self.calls = 0

    def write_rows(self, rows, path: str):
        self.calls += 1
        self.path = path
        self.written.extend(rows)


def test_crawler_deduplicates_and_writes(monkeypatch):
    # Patch classes usadas dentro do módulo app.crawler_service
    monkeypatch.setattr(crawler_module, "SeleniumClient", lambda: FakeClient())
    monkeypatch.setattr(crawler_module, "YahooScreenerPage", FakePage)

    service = crawler_module.CrawlerService()
    service.parser = FakeParser()
    service.writer = FakeWriter()

    total = service.run(region="Brazil", output="out.csv")

    assert total == 3
    assert service.client.closed is True

    assert service.writer.path == "out.csv"
    assert [r["symbol"] for r in service.writer.written] == ["AAA", "BBB", "CCC"]

    # Opcional: garante que houve escrita incremental (2 páginas => até 2 chamadas)
    assert service.writer.calls >= 1


def test_crawler_always_closes_on_exception(monkeypatch):
    monkeypatch.setattr(crawler_module, "SeleniumClient", lambda: FakeClient())

    class ExplodingPage(FakePage):
        def open(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(crawler_module, "YahooScreenerPage", ExplodingPage)

    service = crawler_module.CrawlerService()

    try:
        service.run(region="Brazil", output="out.csv")
        assert False, "Expected exception"
    except RuntimeError as e:
        assert "boom" in str(e)

    assert service.client.closed is True
