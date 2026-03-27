"""Busca de preços via Brapi (REST e SDK)."""
import logging
import os
import time
from datetime import datetime

import requests
import streamlit as st
import yfinance as yf
from brapi import Brapi

logger = logging.getLogger(__name__)

BRAPI_API_KEY = os.getenv("BRAPI_API_KEY", "")
_client = Brapi(api_key=BRAPI_API_KEY)


@st.cache_data(ttl=60 * 30)
def get_last_price(ticker: str) -> float | None:
    """Busca último preço via Brapi SDK com retry exponencial (3 tentativas)."""
    for attempt in range(3):
        try:
            quote = _client.quote.retrieve(tickers=ticker)
            if quote.results:
                result = quote.results[0]
                if hasattr(result, "regular_market_price") and result.regular_market_price:
                    price = float(result.regular_market_price)
                    logger.info("Preço obtido: %s = R$ %.2f", ticker, price)
                    return price
            logger.warning("Preço não encontrado na resposta Brapi para %s", ticker)
            return None
        except Exception as e:
            wait = 2 ** attempt
            logger.warning("Tentativa %d/3 falhou para %s: %s. Aguardando %ds...", attempt + 1, ticker, e, wait)
            if attempt < 2:
                time.sleep(wait)
    logger.error("Todas as tentativas falharam ao buscar preço de %s", ticker)
    return None


@st.cache_data(ttl=60 * 30)
def fetch_ativos_from_brapi(asset_type: str = "fund") -> list[dict]:
    """
    Busca lista de ativos + preço atual via endpoint REST Brapi.
    asset_type: 'fund' (FIIs/ETFs) ou 'stock' (ações).
    """
    try:
        url = f"https://brapi.dev/api/quote/list?type={asset_type}&token={BRAPI_API_KEY}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code == 200:
            stocks = r.json().get("stocks", [])
            logger.info("Brapi type=%s: %d ativos retornados", asset_type, len(stocks))
            return stocks
    except Exception as e:
        logger.warning("Erro ao buscar lista Brapi type=%s: %s", asset_type, e)
    return []


@st.cache_data(ttl=60 * 60 * 6)
def get_benchmark_performance(symbol: str = "IFIX11.SA", period: str = "1y") -> tuple:
    """Busca histórico de um índice via yfinance. Retorna (DataFrame, pct_variação)."""
    fallbacks = {"IFIX11.SA": ["IFIX11.SA", "^IFIX"], "^BVSP": ["^BVSP"]}
    for t in fallbacks.get(symbol, [symbol]):
        try:
            hist = yf.Ticker(t).history(period=period)
            if not hist.empty:
                first, last = hist["Close"].iloc[0], hist["Close"].iloc[-1]
                pct = (last - first) / first * 100
                logger.info("%s (%s): %.2f%%", t, period, pct)
                return hist["Close"].reset_index(), pct
        except Exception as e:
            logger.warning("Erro ao buscar benchmark %s: %s", t, e)
    return None, None
