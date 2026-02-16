from types import SimpleNamespace

from app.pages.yahoo_screener_page import YahooScreenerPage


class FakeEl:
    def __init__(self, attrs=None, text=""):
        self._attrs = attrs or {}
        self.text = text

    def get_attribute(self, name: str):
        return self._attrs.get(name)


class FakeDriver:
    def __init__(self, rows):
        self._rows = rows

    def find_elements(self, by, value):
        # o método _page_signature usa Locators.TABLE_ROWS, que é CSS "table tbody tr"
        # aqui devolve o que foi injetado
        return self._rows


def test_is_disabled_by_disabled_attr():
    el = FakeEl(attrs={"disabled": ""})
    assert YahooScreenerPage._is_disabled(el) is True


def test_is_disabled_by_aria_disabled():
    el = FakeEl(attrs={"aria-disabled": "true"})
    assert YahooScreenerPage._is_disabled(el) is True


def test_is_disabled_by_class_disabled():
    el = FakeEl(attrs={"class": "btn disabled something"})
    assert YahooScreenerPage._is_disabled(el) is True


def test_is_disabled_false():
    el = FakeEl(attrs={"class": "btn", "aria-disabled": "false"})
    assert YahooScreenerPage._is_disabled(el) is False


def test_page_signature_uses_first_3_rows_text():
    rows = [FakeEl(text="r1"), FakeEl(text="r2"), FakeEl(text="r3"), FakeEl(text="r4")]
    client = SimpleNamespace(driver=FakeDriver(rows), wait=None, open=lambda url: None)

    page = YahooScreenerPage(client, debug=False)
    sig = page._page_signature()

    assert sig == "r1\nr2\nr3"
