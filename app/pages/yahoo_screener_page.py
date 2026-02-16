from __future__ import annotations

import hashlib
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
from selenium.webdriver.support.ui import WebDriverWait


@dataclass(frozen=True)
class Locators:
    # ------------------ Filters: Region ------------------
    REGION_MENU_BUTTON = (
        By.XPATH,
        "//button[@aria-haspopup='true' and (contains(@data-ylk,'slk:Region') or .//div[normalize-space()='Region'])]",
    )

    # ------------------ Dialogs (dropdown popovers) ------------------
    DIALOG_CONTAINERS = (By.CSS_SELECTOR, "div.dialog-container.menu-surface-dialog")
    APPLY_BUTTON_IN_DIALOG = (By.XPATH, ".//button[@aria-label='Apply']")
    OPTIONS_LABELS_IN_DIALOG = (By.XPATH, ".//div[contains(@class,'options')]//label")

    # ------------------ Table ------------------
    TABLE = (By.CSS_SELECTOR, "table")
    TBODY = (By.CSS_SELECTOR, "table tbody")
    TABLE_ROWS = (By.CSS_SELECTOR, "table tbody tr")

    # ------------------ Pagination (Yahoo screener table) ------------------
    FIRST_PAGE = (By.CSS_SELECTOR, 'button[data-testid="first-page-button"]')
    PREV_PAGE = (By.CSS_SELECTOR, 'button[data-testid="prev-page-button"]')
    NEXT_PAGE = (By.CSS_SELECTOR, 'button[data-testid="next-page-button"]')
    LAST_PAGE = (By.CSS_SELECTOR, 'button[data-testid="last-page-button"]')

    # ------------------ Rows per page control ------------------    
    # Achar o botão "rows per page" de forma estável (não depender de classes).
    ROWS_PER_PAGE_BUTTON = (
        By.XPATH,
        "//button[@aria-haspopup='listbox' and contains(@data-ylk,'sec:screener-table') and contains(@data-ylk,'subsec:custom-screener')]",
    )
    # Menu listbox que aparece ao clicar no botão (geralmente role=listbox + role=option nos itens)
    LISTBOX_VISIBLE = (
        By.XPATH,
        "//*[@role='listbox' and (not(@aria-hidden) or @aria-hidden='false') and not(contains(@class,'tw-hidden'))]",
    )
    LISTBOX_OPTION_BY_VALUE = (
        By.XPATH,
        ".//*[@role='option' and normalize-space(.)='{value}']"
        "|.//button[normalize-space(.)='{value}']"
        "|.//span[normalize-space(.)='{value}']"
        "|.//*[@data-value='{value}']",
    )

    # ------------------ Empty state (generic) ------------------
    EMPTY_STATE = (
        By.XPATH,
        "//*[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'no results') "
        "or contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'no matching')]",
    )

    # ------------------ Cookie/consent (generic) ------------------
    COOKIE_ACCEPT = (
        By.XPATH,
        "//button[contains(., 'Accept') or contains(., 'I agree') or contains(., 'Agree')]",
    )


class YahooScreenerPage:
    URL = "https://finance.yahoo.com/research-hub/screener/equity/"

    def __init__(self, client, debug: bool = True):
        self.client = client
        self.wait = client.wait  # WebDriverWait padrão do client
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
        self.try_set_rows_per_page(100)
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

        # wait otimizado: primeiro tenta hash de tbody, depois fallback
        self._wait_table_refresh_fast(tbody_before, first_row_before, sig_before)

        sig_after = self._page_signature()
        self._log("Signature AFTER:", sig_after[:200].replace("\n", " | "))

    # ------------------ HTML extraction (OPTIM) ------------------

    def get_table_html(self) -> str:
        """Extrai apenas o HTML da tabela (bem mais leve do que page_source)."""
        table = self.wait.until(EC.presence_of_element_located(Locators.TABLE))
        return table.get_attribute("outerHTML")

    def iter_pages_table_html(self, max_pages: int = 100_000):
        """
        Itera páginas usando o pager da UI.
        Em cada página, yield SOMENTE do HTML da tabela (outerHTML)
        """
        self._wait_results_present_or_empty()
        self._goto_first_page_if_possible()

        page_num = 1
        while page_num <= max_pages:
            self._wait_results_present_or_empty()
            yield self.get_table_html()

            next_btn = self._find(Locators.NEXT_PAGE)
            if not next_btn:
                self._log("iter_pages_table_html(): botão Next não encontrado. Stop.")
                break
            if self._is_disabled(next_btn):
                self._log("iter_pages_table_html(): Next desabilitado (última página). Stop.")
                break

            before_hash = self._tbody_hash()
            tbody_before, first_row_before, sig_before = self._table_snapshot()

            self._log(f"Next: clicando para página {page_num + 1}...")
            self._scroll_into_view(next_btn)
            self._safe_click(next_btn)

            # espera rápida via hash; fallback se falhar
            if not self._wait_table_changed_fast(before_hash, timeout=15, poll=0.2):
                self._log("hash não mudou em 15s; usando refresh robusto (staleness/signature)...")
                self._wait_table_refresh(tbody_before, first_row_before, sig_before)

            page_num += 1

    # ------------------ rows per page (OPTIM) ------------------

    def try_set_rows_per_page(self, value: int = 100) -> bool:
        """
        Tenta setar "rows per page" (25/50/100). Se não achar o controle, não quebra.
        Retorna True se conseguiu selecionar o valor desejado, False caso contrário.
        """
        desired = str(value).strip()
        try:
            btn = self._find(Locators.ROWS_PER_PAGE_BUTTON)
            if not btn:
                self._log("Rows-per-page: controle não encontrado (ok).")
                return False

            current = (btn.get_attribute("aria-label") or btn.get_attribute("title") or "").strip()
            if current == desired:
                self._log(f"Rows-per-page: já está em {desired}.")
                return True

            self._log(f"Rows-per-page: abrindo menu (atual={current!r}, desejado={desired})...")
            before_hash = self._tbody_hash()

            self._scroll_into_view(btn)
            self._safe_click(btn)

            listbox = self._wait_short(6).until(EC.presence_of_element_located(Locators.LISTBOX_VISIBLE))

            # encontrar opção dentro do listbox
            opt_xpath = Locators.LISTBOX_OPTION_BY_VALUE[1].format(value=desired)
            option = None

            # tenta dentro do listbox (mais seguro)
            try:
                option = listbox.find_element(By.XPATH, opt_xpath)
            except Exception:
                # fallback global (às vezes o menu não é filho direto)
                try:
                    option = self.client.driver.find_element(By.XPATH, opt_xpath)
                except Exception:
                    option = None

            if not option:
                self._log(f"Rows-per-page: opção {desired} não encontrada no menu (ok).")
                # tenta fechar clicando no botão novamente
                try:
                    self._safe_click(btn)
                except Exception:
                    pass
                return False

            self._log(f"Rows-per-page: selecionando {desired}...")
            self._safe_click(option)

            # após trocar rows/page, a tabela deve atualizar
            if not self._wait_table_changed_fast(before_hash, timeout=15, poll=0.2):
                self._log("Rows-per-page: hash não mudou; aguardando linhas/empty como fallback...")
                self._wait_results_present_or_empty()

            # conferir de novo o aria-label/title
            btn2 = self._find(Locators.ROWS_PER_PAGE_BUTTON)
            now = (btn2.get_attribute("aria-label") or btn2.get_attribute("title") or "").strip() if btn2 else ""
            ok = (now == desired)
            self._log("Rows-per-page: result =", {"ok": ok, "now": now})
            return ok

        except TimeoutException:
            self._log("Rows-per-page: timeout abrindo listbox/selecionando (ok).")
            return False
        except Exception as e:
            self._log("Rows-per-page: erro inesperado (ok):", repr(e))
            return False

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
            self._log("Timeout esperando popover fechar (seguindo).")

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
        self._log(
            "Apply status:",
            {"enabled": apply_btn.is_enabled(), "disabled_attr": apply_btn.get_attribute("disabled")},
        )

        try:
            self._wait_short(8).until(lambda d: apply_btn.is_enabled())
            self._log("Apply habilitou. Clicando...")
            self._safe_click(apply_btn)
            return True
        except TimeoutException:
            self._log("Apply não habilitou.")
            return False

    # ------------------ wait refresh da tabela (OPTIM) ------------------

    def _tbody_hash(self) -> str:
        """
        Hash rápido do conteúdo do tbody.
        Mais confiável que staleness quando o Yahoo só troca texto/linhas sem recriar nós.
        """
        try:
            tbody = self.client.driver.find_element(*Locators.TBODY)
            txt = (tbody.text or "").strip()
            if not txt:
                return ""
            return hashlib.md5(txt.encode("utf-8")).hexdigest()
        except Exception:
            return ""

    def _wait_table_changed_fast(self, before_hash: str, timeout: int = 15, poll: float = 0.2) -> bool:
        """
        Polling curto (sem WebDriverWait pesado) esperando hash mudar.
        """
        end = time.time() + timeout
        while time.time() < end:
            now = self._tbody_hash()
            if now and now != before_hash:
                return True
            time.sleep(poll)
        return False

    def _wait_table_refresh_fast(self, tbody_before, first_row_before, sig_before: str) -> None:
        """
        Versão otimizada: tenta hash primeiro, depois cai no refresh robusto antigo.
        """
        before_hash = self._tbody_hash()
        # se o hash existe, tenta rápido (evita 25-30s sempre)
        if before_hash:
            if self._wait_table_changed_fast(before_hash, timeout=15, poll=0.2):
                self._wait_results_present_or_empty()
                self._log("Refresh (fast-hash) concluído.")
                return

        # fallback robusto
        self._wait_table_refresh(tbody_before, first_row_before, sig_before)

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
        Fallback robusto (igual o seu), para quando hash/staleness não dão sinal.
        """
        self._log("Aguardando refresh da tabela...")

        if tbody_before is not None:
            try:
                self._wait_short(25).until(EC.staleness_of(tbody_before))
                self._log("tbody stale (re-render).")
                self._wait_results_present_or_empty()
                return
            except TimeoutException:
                self._log("staleness(tbody) não ocorreu em 25s.")

        if first_row_before is not None:
            try:
                self._wait_short(25).until(EC.staleness_of(first_row_before))
                self._log("first_row stale (re-render).")
                self._wait_results_present_or_empty()
                return
            except TimeoutException:
                self._log("staleness(first_row) não ocorreu em 25s.")

        try:
            self._wait_short(20).until(lambda d: self._page_signature() != sig_before)
            self._log("assinatura mudou.")
        except TimeoutException:
            self._log("assinatura não mudou em 20s (pode ser mesmo dataset/ordem).")

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

        before_hash = self._tbody_hash()
        tbody_before, first_row_before, sig_before = self._table_snapshot()

        self._log("Indo para primeira página (first-page)...")
        self._scroll_into_view(btn)
        self._safe_click(btn)

        if not self._wait_table_changed_fast(before_hash, timeout=15, poll=0.2):
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

    def _wait_short(self, seconds: int) -> WebDriverWait:
        # cria um wait com o mesmo driver e timeout menor
        return self.wait.__class__(self.client.driver, seconds)
