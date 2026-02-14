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
    REGION_MENU_BUTTON = (
        By.XPATH,
        "//button[@aria-haspopup='true' and (contains(@data-ylk,'slk:Region') or .//div[normalize-space()='Region'])]",
    )

    DIALOG_CONTAINERS = (By.CSS_SELECTOR, "div.dialog-container.menu-surface-dialog")

    # Dentro do dialog aberto
    APPLY_BUTTON_IN_DIALOG = (By.XPATH, ".//button[@aria-label='Apply']")
    OPTIONS_LABELS_IN_DIALOG = (By.XPATH, ".//div[contains(@class,'options')]//label")

    # tabela
    TBODY = (By.CSS_SELECTOR, "table tbody")
    TABLE_ROWS = (By.CSS_SELECTOR, "table tbody tr")

    # empty
    EMPTY_STATE = (
        By.XPATH,
        "//*[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'no results') "
        "or contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'no matching')]",
    )

    # next
    NEXT_BUTTON = (
        By.XPATH,
        "//button[contains(@aria-label,'Next') or normalize-space()='Next' or .//span[normalize-space()='Next']]",
    )

    COOKIE_ACCEPT = (
        By.XPATH,
        "//button[contains(., 'Accept') or contains(., 'I agree') or contains(., 'Agree')]",
    )


class YahooScreenerPage:
    URL = "https://finance.yahoo.com/research-hub/screener/equity/"

    def __init__(self, client, debug: bool = True):
        self.client = client
        self.wait = client.wait
        self.debug = debug

    # ------------------ logs ------------------

    def _log(self, *args):
        if self.debug:
            print("[YahooScreenerPage]", *args, flush=True)

    # ------------------ públicos ------------------

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

        # ✅ Novo: abrir popover sem depender do aria-controls
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

    def iter_pages_html(self, max_pages: int = 10_000):
        page = 1
        while page <= max_pages:
            self._wait_results_present_or_empty()
            yield self.client.get_page_source()

            if not self.client.driver.find_elements(*Locators.TABLE_ROWS):
                self._log("iter_pages_html(): 0 linhas. Stop.")
                break

            next_btn = self._get_next_button()
            if not next_btn or self._is_disabled(next_btn):
                self._log("iter_pages_html(): sem Next ou desabilitado. Stop.")
                break

            before = self._page_signature()
            self._safe_click(next_btn)
            self._wait_page_signature_changed(before)
            self._log(f"Next: {page} -> {page+1}")
            page += 1

    # ------------------ cookies ------------------

    def _accept_cookies_if_present(self) -> None:
        try:
            btn = self._wait_short(2).until(EC.element_to_be_clickable(Locators.COOKIE_ACCEPT))
            self._log("Cookie/consent detectado. Clicando...")
            self._safe_click(btn)
        except TimeoutException:
            return

    # ------------------ abrir/fechar dialog (ROBUSTO) ------------------

    def _open_region_dialog(self, region_button):
        """
        Abre o dropdown do Region e retorna o dialog_root REAL (o que ficou aberto),
        sem confiar no aria-controls, que pode ser dinâmico.

        Critério do dialog aberto:
        - aria-hidden="false"
        - NÃO tem 'tw-hidden' na classe
        - contém botão Apply e lista de options
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

        # tenta clique (normal + JS fallback)
        self._log("Abrindo popover Region (click)...")
        self._safe_click(region_button)

        def wait_new_open_dialog(drv):
            opened = list_open_dialogs()
            # pode ser que nenhum estava aberto antes e agora apareceu 1
            # ou pode ser que tenha trocado a referência (re-render)
            for dialog in opened:
                try:
                    # verifica conteúdo
                    has_apply = len(dialog.find_elements(*Locators.APPLY_BUTTON_IN_DIALOG)) > 0
                    has_opts = len(dialog.find_elements(*Locators.OPTIONS_LABELS_IN_DIALOG)) > 0
                    if has_apply and has_opts:
                        return dialog
                except Exception:
                    continue
            return False

        try:
            dialog = self._wait_short(10).until(wait_new_open_dialog)
            self._log("Popover aberto (dialog detectado). id=", dialog.get_attribute("id"))
            return dialog
        except TimeoutException:
            self._log("❌ Timeout detectando dialog aberto. Dump debug...")
            self._dump_debug("open_dialog_failed")
            raise

    def _wait_dialog_closed(self, dialog_root) -> None:
        """
        Espera o dialog_root fechar:
        - aria-hidden="true" OU classe contém tw-hidden
        Observação: dialog_root pode ficar stale se re-render fechar/recriar; tratamos isso.
        """
        self._log("Aguardando popover fechar...")
        def closed(_):
            try:
                aria_hidden = (dialog_root.get_attribute("aria-hidden") or "").lower()
                klass = dialog_root.get_attribute("class") or ""
                return (aria_hidden == "true") or ("tw-hidden" in klass)
            except StaleElementReferenceException:
                # se ficou stale, ele foi removido -> fechado
                return True

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

    # ------------------ refresh da tabela ------------------

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
        self._log("Aguardando refresh da tabela (pós-popover)...")

        if tbody_before is not None:
            try:
                self._wait_short(20).until(EC.staleness_of(tbody_before))
                self._log("✅ tbody ficou stale (re-render).")
                self._wait_results_present_or_empty()
                return
            except TimeoutException:
                self._log("staleness(tbody) não ocorreu em 20s.")

        if first_row_before is not None:
            try:
                self._wait_short(20).until(EC.staleness_of(first_row_before))
                self._log("✅ first_row ficou stale (re-render).")
                self._wait_results_present_or_empty()
                return
            except TimeoutException:
                self._log("staleness(first_row) não ocorreu em 20s.")

        try:
            self._wait_short(25).until(lambda d: self._page_signature() != sig_before)
            self._log("✅ assinatura mudou.")
        except TimeoutException:
            self._log("⚠️ assinatura não mudou em 25s.")

        self._wait_results_present_or_empty()
        self._log("Refresh concluído (linhas ou empty).")

    def _wait_results_present_or_empty(self) -> None:
        self.wait.until(
            lambda d: (len(d.find_elements(*Locators.TABLE_ROWS)) > 0)
            or (len(d.find_elements(*Locators.EMPTY_STATE)) > 0)
        )

    # ------------------ paginação helpers ------------------

    def _page_signature(self) -> str:
        rows = self.client.driver.find_elements(*Locators.TABLE_ROWS)[:3]
        return "\n".join(r.text for r in rows)

    def _wait_page_signature_changed(self, before: str) -> None:
        self.wait.until(lambda d: self._page_signature() != before)

    def _get_next_button(self):
        els = self.client.driver.find_elements(*Locators.NEXT_BUTTON)
        return els[0] if els else None

    @staticmethod
    def _is_disabled(el) -> bool:
        disabled_attr = el.get_attribute("disabled")
        aria_disabled = el.get_attribute("aria-disabled")
        klass = (el.get_attribute("class") or "").lower()
        return (disabled_attr is not None) or (aria_disabled == "true") or ("disabled" in klass)

    # ------------------ click helpers ------------------

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

    # ------------------ debug dump ------------------

    def _dump_debug(self, name: str) -> None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        try:
            import os
            os.makedirs("debug", exist_ok=True)
            png = f"debug/{name}-{ts}.png"
            html = f"debug/{name}-{ts}.html"
            self.client.driver.save_screenshot(png)
            with open(html, "w", encoding="utf-8") as f:
                f.write(self.client.driver.page_source)
            self._log("Dump debug:", png, html)
        except Exception as e:
            self._log("Falha ao dump debug:", e)
