"""Web scraping de DY/Dividend Yield via FundsExplorer e StatusInvest."""
import logging
import time

import requests
import streamlit as st
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _scrape_with_retry(url: str, label: str) -> requests.Response | None:
    """GET com retry exponencial (3 tentativas). Retorna response ou None."""
    for attempt in range(3):
        try:
            return requests.get(url, headers=_HEADERS, timeout=10)
        except requests.RequestException as e:
            wait = 2 ** attempt
            logger.warning("%s tentativa %d/3: %s. Aguardando %ds...", label, attempt + 1, e, wait)
            if attempt < 2:
                time.sleep(wait)
    logger.error("%s: todas as tentativas falharam", label)
    return None


def _parse_float(text: str, low: float = 0, high: float = 100) -> float | None:
    """Converte texto em float e valida intervalo. Aceita com ou sem '%'."""
    try:
        v = float(text.replace("%", "").replace(",", ".").strip())
        return v if low < v < high else None
    except (ValueError, AttributeError):
        return None


@st.cache_data(ttl=60 * 60 * 24)
def get_dy_from_fundsexplorer(ticker: str) -> float | None:
    """Busca DY no FundsExplorer (exclusivo para FIIs). Retorna decimal (ex: 0.0846)."""
    url = f"https://www.fundsexplorer.com.br/funds/{ticker.lower()}"
    r = _scrape_with_retry(url, f"FundsExplorer/{ticker}")
    if r is None or r.status_code != 200:
        if r:
            logger.warning("FundsExplorer HTTP %d para %s", r.status_code, ticker)
        return None

    soup = BeautifulSoup(r.content, "html.parser")

    # Estratégia 1: span.indicator-value com %
    for elem in soup.find_all("span", class_="indicator-value"):
        v = _parse_float(elem.get_text().strip(), 0, 50)
        if v:
            logger.info("DY FundsExplorer: %s = %.2f%%", ticker, v)
            return v / 100

    # Estratégia 2: tabela com label "dividend yield" ou "dy"
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            for i, cell in enumerate(cells):
                label = cell.get_text().lower()
                if "dividend yield" in label or " dy" in label:
                    if i + 1 < len(cells):
                        v = _parse_float(cells[i + 1].get_text().strip(), 0, 50)
                        if v:
                            logger.info("DY FundsExplorer (tabela): %s = %.2f%%", ticker, v)
                            return v / 100

    logger.debug("DY não encontrado no FundsExplorer para %s", ticker)
    return None


@st.cache_data(ttl=60 * 60 * 24)
def get_dy_from_statusinvest(ticker: str, asset_type: str = "FII") -> float | None:
    """
    Busca Dividend Yield no StatusInvest pelo label 'Dividend Yield'.
    O site retorna o valor sem '%' (ex: '8,46'). Suporta FIIs, Ações e ETFs.
    """
    path_map = {"FII": "fundos-imobiliarios", "Ação": "acoes", "ETF": "etfs"}
    path = path_map.get(asset_type, "acoes")
    url = f"https://statusinvest.com.br/{path}/{ticker.lower()}"
    r = _scrape_with_retry(url, f"StatusInvest/{ticker}")
    if r is None or r.status_code != 200:
        if r:
            logger.warning("StatusInvest HTTP %d para %s", r.status_code, ticker)
        return None

    soup = BeautifulSoup(r.content, "html.parser")

    # Estratégia 1: localizar pelo label "Dividend Yield" e pegar o .value do bloco pai
    for label_elem in soup.find_all(string=lambda t: t and "Dividend Yield" in t):
        block = label_elem.find_parent("div")
        if block:
            block = block.find_parent("div")
        if block:
            val_elem = block.find(["div", "strong", "span"], class_="value")
            if val_elem:
                v = _parse_float(val_elem.get_text().strip(), 0, 100)
                if v:
                    logger.info("DY StatusInvest: %s = %.2f%%", ticker, v)
                    return v / 100

    # Estratégia 2: fallback numérico — apenas FIIs e Ações (ETFs sem label = dado não confiável)
    if asset_type != "ETF":
        for tag in soup.find_all(["div", "strong", "span"], class_="value"):
            v = _parse_float(tag.get_text().strip(), 0, 50)
            if v:
                logger.info("DY StatusInvest (fallback): %s = %.2f%%", ticker, v)
                return v / 100

    logger.debug("DY não encontrado no StatusInvest para %s", ticker)
    return None


def get_dy_estimate(ticker: str, asset_type: str = "FII") -> float | None:
    """
    Busca DY de múltiplas fontes por prioridade.
    FIIs: FundsExplorer → StatusInvest.
    Ações/ETFs: StatusInvest.
    Retorna decimal (ex: 0.0846) ou None.
    """
    if asset_type == "FII":
        dy = get_dy_from_fundsexplorer(ticker)
        if dy is not None and dy > 0:
            return dy
    return get_dy_from_statusinvest(ticker, asset_type)
