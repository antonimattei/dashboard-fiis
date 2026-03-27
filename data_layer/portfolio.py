"""Persistência e cálculo de métricas do portfolio."""
import json
import logging
import os

import pandas as pd
import streamlit as st

from config import DATA_DIR, PORTFOLIO_JSON, ASSET_CONFIG
from api.prices import get_last_price
from api.scraping import get_dy_estimate
from data_layer.assets import load_ativos_list, classify_ticker

logger = logging.getLogger(__name__)


def load_portfolio() -> dict:
    if not os.path.exists(PORTFOLIO_JSON):
        return {"positions": []}
    try:
        with open(PORTFOLIO_JSON, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {"positions": []}
            data = json.loads(content)
            if not isinstance(data, dict):
                return {"positions": []}
            data.setdefault("positions", [])
            return data
    except json.JSONDecodeError as e:
        logger.error("portfolio.json corrompido: %s", e)
        st.error(f"⚠️ Erro ao ler portfolio.json: {e}")
        st.info("🔄 Criando novo portfolio...")
        new = {"positions": []}
        save_portfolio(new)
        return new
    except Exception as e:
        logger.error("Erro inesperado ao carregar portfolio: %s", e)
        st.error(f"❌ Erro inesperado: {e}")
        return {"positions": []}


def save_portfolio(data: dict) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if not isinstance(data, dict):
            data = {"positions": []}
        data.setdefault("positions", [])
        with open(PORTFOLIO_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Erro ao salvar portfolio: %s", e)
        st.error(f"❌ Erro ao salvar portfolio: {e}")


def upsert_position(portfolio: dict, ticker: str, quantity: int, buy_price: float) -> None:
    """Insere ou atualiza posição. Compra recalcula PM; venda mantém PM."""
    ticker = ticker.upper()
    for pos in portfolio["positions"]:
        if pos["ticker"] == ticker:
            old_qty, old_pm = pos["quantity"], pos["avg_price"]
            new_qty = old_qty + quantity
            if new_qty <= 0:
                pos["quantity"] = 0
                pos["avg_price"] = 0
            elif quantity > 0:
                pos["avg_price"] = (old_qty * old_pm + quantity * buy_price) / new_qty
                pos["quantity"] = new_qty
            else:
                pos["quantity"] = new_qty  # venda: PM não muda
            return
    portfolio["positions"].append({
        "ticker": ticker, "quantity": quantity, "avg_price": buy_price
    })


def clean_positions(portfolio: dict) -> None:
    portfolio["positions"] = [p for p in portfolio["positions"] if p["quantity"] > 0]


def calc_portfolio_metrics(portfolio: dict) -> tuple[pd.DataFrame, dict]:
    """Calcula métricas de todas as posições. Usa CSV como cache, cai na API se necessário."""
    df_ativos = load_ativos_list()
    rows = []

    for p in portfolio["positions"]:
        ticker = p["ticker"]
        qty = p["quantity"]
        pm = p["avg_price"]
        asset_type = classify_ticker(ticker)

        cached = df_ativos[df_ativos["ticker"] == ticker]
        if not cached.empty and float(cached.iloc[0]["preco_atual"]) > 0:
            price = float(cached.iloc[0]["preco_atual"])
            dy = float(cached.iloc[0]["dy_12m"])  # já em %
        else:
            price = get_last_price(ticker) or 0.0
            dy_raw = get_dy_estimate(ticker, asset_type)
            dy = (dy_raw * 100) if dy_raw is not None else 0.0

        market = qty * price
        change = (price - pm) / pm * 100 if pm > 0 else 0.0
        monthly_income = (dy / 100 * price / 12.0) * qty

        rows.append({
            "Ticker": ticker,
            "Tipo": asset_type,
            "Qtde": qty,
            "PM (R$)": pm,
            "Preço Atual (R$)": price,
            "Variação (%)": change,
            "DY/Yield 12m (%)": dy,
            "Valor de Mercado (R$)": market,
            "Renda Mensal Est. (R$)": monthly_income,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        pat = df["Valor de Mercado (R$)"].sum()
        renda = df["Renda Mensal Est. (R$)"].sum()
        dy_medio = (renda * 12) / pat * 100 if pat > 0 else 0.0
        totals = {"Patrimônio (R$)": pat, "Renda Mensal (R$)": renda, "DY Médio (%)": dy_medio}
    else:
        totals = {"Patrimônio (R$)": 0.0, "Renda Mensal (R$)": 0.0, "DY Médio (%)": 0.0}

    return df, totals
