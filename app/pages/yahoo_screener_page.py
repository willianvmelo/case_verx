# app/pages/yahoo_screener_page.py

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
    NoSuchElementException,
)


@dataclass(frozen=True)
class Locators:
    # Filter button (Region)
    REGION_MENU_BUTTON = (
        By.XPATH,
        "//button[@aria-haspopup='true' and (contains(@data-ylk,'slk:Region') or .//div[normalize-space()='Region'])]",
    )

    # Dialogs (dropdown popovers)
    DIALOG_CONTAINERS = (By.CSS_SELECTOR, "div.dialog-container.menu-surface-dialog")
    APPLY_BUTTON_IN_DIALOG = (By.XPATH, ".//button[@aria-label='Apply']")
    OPTIONS_LABELS_IN_DIALOG = (By.XPATH, ".//div[contains(@class,'options')]//label")

    # Table
    TBODY = (By.CSS_SELECTOR, "table tbody")
    TABLE_ROWS = (By.CSS_SELECTOR, "table tbody tr")

    # Pagination buttons (Yahoo screener table)
    FIRST_PAGE = (By.CSS_SELECTOR, 'button[data-testid="first-page-button"]')
    PREV_PAGE = (By.CSS_SELECTOR, 'button[data-testid="prev-page-button"]')
    NEXT_PAGE = (By.CSS_SELECTOR, 'button[data-testid="next-page-button"]')
    LAST_PAGE = (By.CSS_SELECTOR, 'button[data-testid="last-page-button"]')

    # Empty state (generic)
    EMPTY_STATE = (
        By.XPATH,
        "//*[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'no results') "
        "or contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'no matching')]",
    )

    # Cookie/consent (generic)
    COOKIE_ACCEPT = (
        By.XPATH,
        "//button[contains(., 'Accept') or contains(., 'I agree') or contains(., 'Agree')]",
    )


class YahooScreenerPage:
    URL = "https://finance.yahoo.com/research-hub/screener/equity/?start=0&count=100"

    def __init__(self, client, debug: bool = True):
        self.client = client
        self.wait = client.wait
        self.debug = debug

    # ------------------ logs ------------------

    def _log(self, *args):
        if self.debug:
            print("[YahooScreenerPage]", *args, flush=True)

    # ------------------ public ------------------

    def open(self) -> None:
        self.client.open(self.URL)
        self._accept_cookies_if_present()
        self._wait_results_present_or_empty()
        self._log("open(): página pronta (linhas ou empty-state).")

    def apply_region(self, region: str) -> None:
        target_norm = region.strip().lower()
        self._log(f"apply_region('{region}') target_norm='{target_norm}'")

        tbody_before, first_row_before, sig_before = self._table_snapshot()
        self._log("Snapshot antes:", {"has_tbody": bool(tbody_before), "has_row": bool(first_row_before)})

        btn = self.wait.until(EC.presence_of_element_located(Locators.REGION_MENU_BUTTON))
        self._scroll_into_view(btn)

        dialog = self._open_region_dialog(btn)

        before_checked = self._get_checked_regions(dialog)
        self._log("Checked BEFORE:", before_checked)

        self._ensure_only_target_checked(dialog, target_norm)

        after_checked = self._get_checked_regions(dialog)
        self._log("Checked AFTER:", after_checked)

        clicked_apply = self._click_apply_if_enabled(dialog)
        self._log("Apply clicked?", clicked_apply)

        self._wait_dialog_closed(dialog)
        self._wait_table_refresh(tbody_before, first_row_before, sig_before)

        sig_after = self._page_signature()
        self._log("Signature AFTER:", sig_after[:200].replace("\n", " | "))

    def iter_pages_html(self, max_pages: int = 100_000):
        """
        Itera todas as páginas usando o botão Next do pager.
        Para cada página, yield do HTML atual (após a tabela estar "pronta").
        """
        # garante estado pronto antes de começar
        self._wait_results_present_or_empty()

        # opcional: força ir para primeira página
        self._goto_first_page_if_possible()

        page_num = 1
        while page_num <= max_pages:
            self._wait_results_present_or_empty()
            yield self.client.get_page_source()

            next_btn = self._find(Locators.NEXT_PAGE)
            if not next_btn:
                self._log("iter_pages_html(): botão Next não encontrado. Stop.")
                break

            if self._is_disabled(next_btn):
                self._log("iter_pages_html(): Next desabilitado (última página). Stop.")
                break

            # Snapshot antes do clique (pra esperar refresh)
            tbody_before, first_row_before, sig_before = self._table_snapshot()
            self._log(f"Next: clicando para página {page_num + 1}...")

            self._scroll_into_view(next_btn)
            self._safe_click(next_btn)

            # ✅ espera a tabela de fato atualizar (delay pós-clique)
            self._wait_table_refresh(tbody_before, first_row_before, sig_before)

            page_num += 1

    # ------------------ cookies ------------------

    def _accept_cookies_if_present(self) -> None:
        try:
            btn = self._wait_short(2).until(EC.element_to_be_clickable(Locators.COOKIE_ACCEPT))
            self._log("Cookie/consent detectado. Clicando...")
            self._safe_click(btn)
        except TimeoutException:
            return

    # ------------------ dialog open/close (robust) ------------------

    def _open_region_dialog(self, region_button):
        """
        Abre o dropdown do Region e retorna o dialog_root real,
        sem depender de aria-controls.
        """

        def list_open_dialogs() -> List[object]:
            dialogs = self.client.driver.find_elements(*Locators.DIALOG_CONTAINERS)
            opened = []
            for d in dialogs:
                try:
                    aria_hidden = (d.get_attribute("aria-hidden") or "").lower()
                    klass = d.get_attribute("class") or ""
                    if aria_hidden == "false" and "tw-hidden" not in klass:
                        opened.append(d)
                except Exception:
                    continue
            return opened

        before_open = list_open_dialogs()
        self._log("Dialogs abertos ANTES:", len(before_open))

        self._log("Abrindo popover Region (click)...")
        self._safe_click(region_button)

        def wait_open_dialog(_):
            opened = list_open_dialogs()
            for dialog in opened:
                try:
                    has_apply = len(dialog.find_elements(*Locators.APPLY_BUTTON_IN_DIALOG)) > 0
                    has_opts = len(dialog.find_elements(*Locators.OPTIONS_LABELS_IN_DIALOG)) > 0
                    if has_apply and has_opts:
                        return dialog
                except Exception:
                    continue
            return False

        dialog = self._wait_short(10).until(wait_open_dialog)
        self._log("Popover aberto (dialog detectado). id=", dialog.get_attribute("id"))
        return dialog

    def _wait_dialog_closed(self, dialog_root) -> None:
        self._log("Aguardando popover fechar...")

        def closed(_):
            try:
                aria_hidden = (dialog_root.get_attribute("aria-hidden") or "").lower()
                klass = dialog_root.get_attribute("class") or ""
                return (aria_hidden == "true") or ("tw-hidden" in klass)
            except StaleElementReferenceException:
                return True  # removido do DOM -> fechado

        try:
            self._wait_short(10).until(closed)
            self._log("Popover fechado.")
        except TimeoutException:
            self._log("⚠️ Timeout esperando popover fechar (seguindo).")

    # ------------------ toggle checkboxes ------------------

    def _get_option_labels(self, dialog_root):
        return dialog_root.find_elements(*Locators.OPTIONS_LABELS_IN_DIALOG)

    def _get_checked_regions(self, dialog_root) -> List[str]:
        checked: List[str] = []
        for label in self._get_option_labels(dialog_root):
            try:
                name = label.find_element(By.XPATH, ".//span").text.strip()
                cb = label.find_element(By.XPATH, ".//input[@type='checkbox']")
                if cb.is_selected():
                    checked.append(name)
            except Exception:
                continue
        return checked

    def _find_label_by_name(self, dialog_root, target_norm: str):
        for label in self._get_option_labels(dialog_root):
            try:
                name = label.find_element(By.XPATH, ".//span").text.strip()
                if name.lower() == target_norm:
                    return label
            except Exception:
                continue
        try:
            return dialog_root.find_element(
                By.XPATH,
                f".//div[contains(@class,'options')]//label[translate(@aria-label,"
                f"'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='{target_norm}']"
                f"|.//div[contains(@class,'options')]//label[translate(@title,"
                f"'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='{target_norm}']",
            )
        except Exception:
            return None

    def _ensure_only_target_checked(self, dialog_root, target_norm: str) -> None:
        self._log("Toggle: deixando SOMENTE marcado:", target_norm)

        target_label = self._find_label_by_name(dialog_root, target_norm)
        if target_label is None:
            raise RuntimeError(f"Região alvo '{target_norm}' não encontrada na lista.")

        def target_selected() -> bool:
            return target_label.find_element(By.XPATH, ".//input[@type='checkbox']").is_selected()

        # desmarcar todos != alvo
        for label in self._get_option_labels(dialog_root):
            try:
                name = label.find_element(By.XPATH, ".//span").text.strip()
                cb = label.find_element(By.XPATH, ".//input[@type='checkbox']")
            except Exception:
                continue
            if name.lower() == target_norm:
                continue
            if cb.is_selected():
                self._log("Desmarcando:", name)
                self._safe_click(label)

        # marcar alvo
        if not target_selected():
            self._log("Marcando alvo:", target_norm)
            self._safe_click(target_label)
            self.wait.until(lambda d: target_selected())

        final_checked = self._get_checked_regions(dialog_root)
        self._log("Marcados FINAL:", final_checked)

    # ------------------ Apply ------------------

    def _click_apply_if_enabled(self, dialog_root) -> bool:
        apply_btn = dialog_root.find_element(*Locators.APPLY_BUTTON_IN_DIALOG)
        self._log("Apply status:", {"enabled": apply_btn.is_enabled(), "disabled_attr": apply_btn.get_attribute("disabled")})

        try:
            self._wait_short(8).until(lambda d: apply_btn.is_enabled())
            self._log("Apply habilitou. Clicando...")
            self._safe_click(apply_btn)
            return True
        except TimeoutException:
            self._log("⚠️ Apply não habilitou.")
            return False

    # ------------------ wait refresh da tabela ------------------

    def _table_snapshot(self) -> Tuple[Optional[object], Optional[object], str]:
        tbody_el = None
        row_el = None
        try:
            tbody_el = self.client.driver.find_element(*Locators.TBODY)
        except NoSuchElementException:
            pass
        try:
            rows = self.client.driver.find_elements(*Locators.TABLE_ROWS)
            row_el = rows[0] if rows else None
        except Exception:
            row_el = None
        return tbody_el, row_el, self._page_signature()

    def _wait_table_refresh(self, tbody_before, first_row_before, sig_before: str) -> None:
        """
        Após clique em Next (ou Apply), a tabela demora pra atualizar.
        Esperamos sinais reais de re-render / mudança.
        """
        self._log("Aguardando refresh da tabela...")

        if tbody_before is not None:
            try:
                self._wait_short(25).until(EC.staleness_of(tbody_before))
                self._log("✅ tbody stale (re-render).")
                self._wait_results_present_or_empty()
                return
            except TimeoutException:
                self._log("staleness(tbody) não ocorreu em 25s.")

        if first_row_before is not None:
            try:
                self._wait_short(25).until(EC.staleness_of(first_row_before))
                self._log("✅ first_row stale (re-render).")
                self._wait_results_present_or_empty()
                return
            except TimeoutException:
                self._log("staleness(first_row) não ocorreu em 25s.")

        try:
            self._wait_short(30).until(lambda d: self._page_signature() != sig_before)
            self._log("✅ assinatura mudou.")
        except TimeoutException:
            self._log("⚠️ assinatura não mudou em 30s (pode ser mesmo dataset/ordem).")

        self._wait_results_present_or_empty()
        self._log("Refresh concluído (linhas ou empty).")

    def _wait_results_present_or_empty(self) -> None:
        self.wait.until(
            lambda d: (len(d.find_elements(*Locators.TABLE_ROWS)) > 0)
            or (len(d.find_elements(*Locators.EMPTY_STATE)) > 0)
        )

    # ------------------ pager: first page ------------------

    def _goto_first_page_if_possible(self) -> None:
        btn = self._find(Locators.FIRST_PAGE)
        if not btn:
            return
        if self._is_disabled(btn):
            self._log("First-page já desabilitado (já estamos na primeira).")
            return

        tbody_before, first_row_before, sig_before = self._table_snapshot()
        self._log("Indo para primeira página (first-page)...")
        self._scroll_into_view(btn)
        self._safe_click(btn)
        self._wait_table_refresh(tbody_before, first_row_before, sig_before)

    # ------------------ misc helpers ------------------

    def _find(self, locator):
        try:
            els = self.client.driver.find_elements(*locator)
            return els[0] if els else None
        except Exception:
            return None

    def _page_signature(self) -> str:
        rows = self.client.driver.find_elements(*Locators.TABLE_ROWS)[:3]
        return "\n".join(r.text for r in rows)

    def _wait_page_signature_changed(self, before: str) -> None:
        self.wait.until(lambda d: self._page_signature() != before)

    @staticmethod
    def _is_disabled(el) -> bool:
        disabled_attr = el.get_attribute("disabled")
        aria_disabled = el.get_attribute("aria-disabled")
        klass = (el.get_attribute("class") or "").lower()
        return (disabled_attr is not None) or (aria_disabled == "true") or ("disabled" in klass)

    def _safe_click(self, el) -> None:
        try:
            el.click()
        except (ElementClickInterceptedException, StaleElementReferenceException):
            self.client.driver.execute_script("arguments[0].click();", el)

    def _scroll_into_view(self, el) -> None:
        try:
            self.client.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        except Exception:
            return

    def _wait_short(self, seconds: int):
        return self.wait.__class__(self.client.driver, seconds)
