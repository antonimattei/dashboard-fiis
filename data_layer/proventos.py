"""Persistência do histórico de proventos/dividendos recebidos."""
import json
import logging
import os

import streamlit as st

from config import DATA_DIR, PROVENTOS_JSON

logger = logging.getLogger(__name__)


def load_proventos() -> list[dict]:
    if not os.path.exists(PROVENTOS_JSON):
        return []
    try:
        with open(PROVENTOS_JSON, "r", encoding="utf-8") as f:
            data = json.loads(f.read().strip() or "[]")
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error("Erro ao carregar proventos: %s", e)
        return []


def save_proventos(proventos: list[dict]) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(PROVENTOS_JSON, "w", encoding="utf-8") as f:
            json.dump(proventos, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Erro ao salvar proventos: %s", e)
        st.error(f"❌ Erro ao salvar proventos: {e}")


def add_provento(ticker: str, data_pagamento: str, valor_por_cota: float, quantidade: int) -> None:
    proventos = load_proventos()
    proventos.append({
        "ticker": ticker.upper(),
        "data": data_pagamento,
        "valor_por_cota": valor_por_cota,
        "quantidade": quantidade,
        "total": round(valor_por_cota * quantidade, 2),
    })
    proventos.sort(key=lambda x: x["data"], reverse=True)
    save_proventos(proventos)
