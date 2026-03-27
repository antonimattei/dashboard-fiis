"""Utilitários compartilhados: formatação, simulação e helpers de UI."""
from datetime import datetime

import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta

from config import ASSET_CONFIG


def brl(value: float) -> str:
    """Formata valor em reais no padrão brasileiro. Ex: R$ 1.234,56"""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(value: float) -> str:
    """Formata percentual no padrão brasileiro. Ex: 8,46%"""
    return f"{value:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def simulate_projection(
    start_capital: float,
    current_monthly_income: float,
    monthly_contribution: float,
    target_monthly_income: float,
    yearly_return: float = 0.06,
    yearly_dividend_growth: float = 0.02,
    yearly_contrib_growth: float = 0.00,
    max_years: int = 40,
) -> tuple[pd.DataFrame, int | None]:
    """
    Simula crescimento de patrimônio e renda mensal até atingir meta de IF.
    Retorna (DataFrame com série temporal, mês em que a meta foi atingida ou None).
    """
    r_m = (1 + yearly_return) ** (1 / 12) - 1
    g_div_m = (1 + yearly_dividend_growth) ** (1 / 12) - 1
    g_contrib_m = (1 + yearly_contrib_growth) ** (1 / 12) - 1
    monthly_yield = current_monthly_income / start_capital if start_capital > 0 else 0.007

    today = datetime.today()
    dates, wealth_pts, income_pts = [], [], []
    wealth = start_capital
    income = current_monthly_income
    found_months = None

    for month in range(max_years * 12):
        dates.append(today + relativedelta(months=month))
        wealth_pts.append(wealth)
        income_pts.append(income)
        if income >= target_monthly_income and found_months is None:
            found_months = month
        monthly_yield *= (1 + g_div_m)
        monthly_contribution *= (1 + g_contrib_m)
        income = wealth * monthly_yield
        wealth = wealth * (1 + r_m) + monthly_contribution

    return pd.DataFrame({
        "Data": dates,
        "Patrimônio (R$)": wealth_pts,
        "Renda Mensal (R$)": income_pts,
    }), found_months


def highlight_dy(row: pd.Series, dy_min: float, dy_max: float) -> list[str]:
    """Aplica cor de fundo na linha da tabela conforme o DY."""
    dy = row.get("DY/Yield 12m (%)", 0)
    if dy > 0 and dy < dy_min:
        return ["background-color: #ffe5e5"] * len(row)
    if dy >= dy_max:
        return ["background-color: #fff3cd"] * len(row)
    return [""] * len(row)
