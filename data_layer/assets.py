"""Gerenciamento da lista de ativos (FIIs, Ações, ETFs)."""
import logging
import os
import time
from datetime import datetime

import pandas as pd
import streamlit as st

from config import (
    ATIVOS_CSV, DATA_DIR, ETFS_BR,
    FIIS_FALLBACK, ACOES_FALLBACK,
)
from api.prices import fetch_ativos_from_brapi

logger = logging.getLogger(__name__)


def classify_ticker(ticker: str) -> str:
    """Classifica o tipo do ativo pelo sufixo do ticker."""
    t = ticker.upper()
    if t in ETFS_BR:
        return "ETF"
    if t.endswith("11"):
        return "FII"
    return "Ação"


def _build_ativos_list() -> list[dict]:
    """Monta lista unificada de FIIs, ETFs e Ações com preços da Brapi."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    ativos = []

    # Fundos (FIIs + ETFs)
    for s in fetch_ativos_from_brapi("fund"):
        ticker = s.get("stock", "").upper()
        if not ticker.endswith("11"):
            continue
        tipo = "ETF" if ticker in ETFS_BR else "FII"
        ativos.append({
            "ticker": ticker,
            "nome": s.get("name", ticker),
            "tipo": tipo,
            "preco_atual": float(s.get("close") or 0.0),
            "dy_12m": 0.0,
            "data_atualizacao": now_str if s.get("close") else "",
        })

    # Ações (exclui fundos e BDRs)
    for s in fetch_ativos_from_brapi("stock"):
        ticker = s.get("stock", "").upper()
        if ticker.endswith("11") or ticker.endswith("34") or ticker.endswith("32"):
            continue
        ativos.append({
            "ticker": ticker,
            "nome": s.get("name", ticker),
            "tipo": "Ação",
            "preco_atual": float(s.get("close") or 0.0),
            "dy_12m": 0.0,
            "data_atualizacao": now_str if s.get("close") else "",
        })

    if not ativos:
        logger.warning("Brapi indisponível — usando fallback offline")
        for t in FIIS_FALLBACK:
            ativos.append({"ticker": t, "nome": t, "tipo": "FII",
                           "preco_atual": 0.0, "dy_12m": 0.0, "data_atualizacao": ""})
        for t in ACOES_FALLBACK:
            ativos.append({"ticker": t, "nome": t, "tipo": "Ação",
                           "preco_atual": 0.0, "dy_12m": 0.0, "data_atualizacao": ""})
        for t in ETFS_BR:
            ativos.append({"ticker": t, "nome": t, "tipo": "ETF",
                           "preco_atual": 0.0, "dy_12m": 0.0, "data_atualizacao": ""})

    logger.info("Lista total: %d ativos", len(ativos))
    return ativos


def load_ativos_list() -> pd.DataFrame:
    """
    Carrega lista de ativos com prioridade:
    1. CSV em disco com menos de 30 min (cache local)
    2. Brapi REST (lista + preços em uma chamada)
    3. Fallback offline
    """
    if os.path.exists(ATIVOS_CSV):
        try:
            age_min = (time.time() - os.path.getmtime(ATIVOS_CSV)) / 60
            if age_min < 30:
                df = pd.read_csv(ATIVOS_CSV)
                df["ticker"] = df["ticker"].str.upper().str.strip()
                for col, default in [("preco_atual", 0.0), ("dy_12m", 0.0),
                                     ("data_atualizacao", ""), ("tipo", "FII")]:
                    if col not in df.columns:
                        df[col] = default
                logger.info("CSV cache carregado (%.0f min atrás, %d ativos)", age_min, len(df))
                return df
        except Exception as e:
            logger.warning("CSV corrompido, recriando: %s", e)

    df = pd.DataFrame(_build_ativos_list()).sort_values(["tipo", "ticker"]).reset_index(drop=True)
    save_ativos_list(df)
    return df


def save_ativos_list(df: pd.DataFrame) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(ATIVOS_CSV, index=False, encoding="utf-8")
