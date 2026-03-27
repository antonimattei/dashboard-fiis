"""Página: Explorar Ativos Brasileiros."""
from datetime import datetime

import streamlit as st

from api.scraping import get_dy_estimate
from data_layer.assets import classify_ticker, load_ativos_list, save_ativos_list
from data_layer.portfolio import clean_positions, load_portfolio, save_portfolio, upsert_position
from utils import brl


def render() -> None:
    st.header("🔍 Explorar Ativos Brasileiros")
    df_ativos = load_ativos_list()

    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        search = st.text_input("Buscar por ticker ou nome", "").strip().upper()
    with col_f2:
        tipo_filtro = st.selectbox("Tipo", ["Todos", "FII", "Ação", "ETF"])

    df_view = df_ativos.copy()
    if search:
        df_view = df_view[
            df_view["ticker"].str.contains(search, na=False) |
            df_view["nome"].str.upper().str.contains(search, na=False)
        ]
    if tipo_filtro != "Todos":
        df_view = df_view[df_view["tipo"] == tipo_filtro]

    df_display = df_view[["ticker", "nome", "tipo", "preco_atual", "dy_12m", "data_atualizacao"]].copy()
    df_display.columns = ["Ticker", "Nome", "Tipo", "Preço Atual (R$)", "DY/Yield 12m (%)", "Última Atualização"]

    st.caption(f"📋 {len(df_view)} ativos | 💡 Preços atualizados a cada 30 min via Brapi")
    st.info("📊 **DY/Yield:** FIIs → FundsExplorer + StatusInvest | Ações/ETFs → StatusInvest")

    if st.button("🔄 Atualizar DY dos ativos visíveis"):
        with st.spinner("Buscando DY via web scraping..."):
            total = len(df_view)
            progress_bar = st.progress(0.0)
            data_att = datetime.now().strftime("%Y-%m-%d %H:%M")

            for i, (_, row) in enumerate(df_view.iterrows()):
                ticker = row["ticker"]
                asset_type = row.get("tipo", classify_ticker(ticker))
                dy = get_dy_estimate(ticker, asset_type)
                df_ativos.loc[df_ativos["ticker"] == ticker, "dy_12m"] = (dy * 100) if dy is not None else 0.0
                df_ativos.loc[df_ativos["ticker"] == ticker, "data_atualizacao"] = data_att
                progress_bar.progress((i + 1) / total)

            save_ativos_list(df_ativos)
            progress_bar.empty()
            st.success(f"✅ DY atualizado para {total} ativos em {data_att}!")
            st.rerun()

    st.dataframe(df_display, use_container_width=True)

    st.subheader("➕ Adicionar posição à carteira")
    col1, col2, col3 = st.columns(3)
    with col1:
        ticker_input = st.text_input("Ticker (ex: HGLG11, ITUB4, BOVA11)", "")
    with col2:
        qty = st.number_input("Quantidade", min_value=1, value=10, step=1)
    with col3:
        buy_price = st.number_input("Preço de compra (R$)", min_value=0.0, value=100.0, step=0.1, format="%.2f")

    if st.button("✅ Adicionar à carteira"):
        if ticker_input:
            portfolio = load_portfolio()
            upsert_position(portfolio, ticker_input.upper(), qty, buy_price)
            clean_positions(portfolio)
            save_portfolio(portfolio)
            tipo_det = classify_ticker(ticker_input)
            st.success(f"✅ {qty}x {ticker_input.upper()} ({tipo_det}) adicionado à carteira!")
            st.balloons()
            st.rerun()
        else:
            st.error("❌ Informe um ticker válido.")
