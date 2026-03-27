"""Página: Minha Carteira."""
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api.prices import get_benchmark_performance
from config import ASSET_CONFIG
from data_layer.portfolio import (
    calc_portfolio_metrics,
    clean_positions,
    load_portfolio,
    save_portfolio,
    upsert_position,
)
from data_layer.proventos import add_provento, load_proventos
from utils import brl, highlight_dy, pct


def render(dy_min: float = 6.0, dy_max: float = 15.0) -> None:
    st.header("💼 Minha Carteira")
    portfolio = load_portfolio()

    with st.spinner("Carregando dados da carteira..."):
        df, totals = calc_portfolio_metrics(portfolio)

    col1, col2, col3 = st.columns(3)
    col1.metric("💰 Patrimônio Total", brl(totals["Patrimônio (R$)"]))
    col2.metric("📈 Renda Mensal Est.", brl(totals["Renda Mensal (R$)"]))
    col3.metric("📊 DY/Yield Médio", pct(totals["DY Médio (%)"]))

    if df.empty:
        st.info("📭 Sua carteira está vazia. Adicione ativos na aba 'Explorar'.")
    else:
        # Alertas de DY
        alertas_baixo = df[(df["DY/Yield 12m (%)"] > 0) & (df["DY/Yield 12m (%)"] < dy_min)]
        alertas_alto = df[df["DY/Yield 12m (%)"] >= dy_max]
        if not alertas_baixo.empty:
            st.warning(f"⚠️ DY/Yield abaixo de {dy_min:.1f}%: **{', '.join(alertas_baixo['Ticker'].tolist())}**")
        if not alertas_alto.empty:
            st.info(f"🟡 DY/Yield acima de {dy_max:.1f}% (verifique risco): **{', '.join(alertas_alto['Ticker'].tolist())}**")

        styled = df.style.format({
            "PM (R$)": "R$ {:.2f}",
            "Preço Atual (R$)": "R$ {:.2f}",
            "Variação (%)": "{:+.2f}%",
            "DY/Yield 12m (%)": "{:.2f}%",
            "Valor de Mercado (R$)": "R$ {:.2f}",
            "Renda Mensal Est. (R$)": "R$ {:.2f}",
        }).apply(highlight_dy, dy_min=dy_min, dy_max=dy_max, axis=1)
        st.dataframe(styled, use_container_width=True)
        st.caption(f"🔴 DY < {dy_min:.1f}%  |  🟡 DY ≥ {dy_max:.1f}%  (ajuste na barra lateral)")

        # ---- Alocação ----
        st.markdown("---")
        st.subheader("📊 Alocação da Carteira")
        col_pie, col_bar = st.columns(2)

        with col_pie:
            fig_pie = go.Figure(go.Pie(
                labels=df["Ticker"],
                values=df["Valor de Mercado (R$)"],
                hole=0.4,
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}<extra></extra>",
            ))
            fig_pie.update_layout(title="Participação por ativo (%)", showlegend=False, height=380,
                                  margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_bar:
            df_sorted = df.sort_values("Valor de Mercado (R$)", ascending=True)
            fig_bar = go.Figure(go.Bar(
                x=df_sorted["Valor de Mercado (R$)"],
                y=df_sorted["Ticker"],
                orientation="h",
                text=df_sorted["Valor de Mercado (R$)"].apply(lambda v: f"R$ {v:,.0f}"),
                textposition="outside",
                marker_color="royalblue",
                hovertemplate="<b>%{y}</b><br>R$ %{x:,.2f}<extra></extra>",
            ))
            fig_bar.update_layout(title="Valor de Mercado por ativo (R$)", height=380,
                                  xaxis=dict(title="R$"), yaxis=dict(title=""),
                                  margin=dict(t=40, b=0, l=0, r=10))
            st.plotly_chart(fig_bar, use_container_width=True)

        if df["Tipo"].nunique() > 1:
            df_tipo = df.groupby("Tipo")["Valor de Mercado (R$)"].sum().reset_index()
            fig_tipo = go.Figure(go.Pie(
                labels=df_tipo["Tipo"],
                values=df_tipo["Valor de Mercado (R$)"],
                hole=0.4,
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}<extra></extra>",
            ))
            fig_tipo.update_layout(title="Alocação por tipo de ativo", height=300,
                                   margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_tipo, use_container_width=True)

        # ---- Comparativo vs benchmark ----
        st.markdown("---")
        st.subheader("📈 Comparativo vs Benchmark")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            benchmark_opt = st.selectbox("Benchmark", ["IFIX (FIIs)", "Ibovespa"], key="bench_sel")
        with col_b2:
            period_map = {"1 mês": "1mo", "3 meses": "3mo", "6 meses": "6mo",
                          "1 ano": "1y", "2 anos": "2y"}
            period_label = st.selectbox("Período", list(period_map.keys()), index=3, key="bench_period")
        period_code = period_map[period_label]
        bench_symbol = "IFIX11.SA" if "IFIX" in benchmark_opt else "^BVSP"

        with st.spinner(f"Buscando {benchmark_opt}..."):
            hist_bench, bench_pct = get_benchmark_performance(bench_symbol, period_code)

        total_mercado = df["Valor de Mercado (R$)"].sum()
        if total_mercado > 0:
            pesos = df["Valor de Mercado (R$)"] / total_mercado
            carteira_pct = (df["Variação (%)"] * pesos).sum()
        else:
            carteira_pct = 0.0

        col_c1, col_c2, col_c3 = st.columns(3)
        col_c1.metric("📊 Sua carteira (vs PM)", f"{carteira_pct:+.2f}%")
        if bench_pct is not None:
            diff = carteira_pct - bench_pct
            col_c2.metric(f"{benchmark_opt} ({period_label})", f"{bench_pct:+.2f}%")
            col_c3.metric("⚖️ Alpha", f"{diff:+.2f}%", delta_color="normal")
        else:
            col_c2.metric(benchmark_opt, "Indisponível")
            col_c3.metric("⚖️ Alpha", "—")

        if hist_bench is not None and not hist_bench.empty:
            hist_norm = hist_bench.copy()
            hist_norm["Base 100"] = hist_norm["Close"] / hist_norm["Close"].iloc[0] * 100
            fig_comp = go.Figure()
            fig_comp.add_trace(go.Scatter(
                x=hist_norm["Date"], y=hist_norm["Base 100"],
                name=benchmark_opt, line=dict(color="darkorange", width=2),
                hovertemplate=f"<b>{benchmark_opt}</b><br>%{{x}}<br>Base 100: %{{y:.1f}}<extra></extra>",
            ))
            fig_comp.add_hline(
                y=100 + carteira_pct, line_dash="dash", line_color="royalblue",
                annotation_text=f"Sua carteira: {100 + carteira_pct:.1f}",
                annotation_position="right",
            )
            fig_comp.update_layout(
                title=f"{benchmark_opt} — {period_label} (base 100)",
                xaxis=dict(title="Data"), yaxis=dict(title="Base 100"),
                height=350, margin=dict(t=40, b=0, l=0, r=10),
            )
            st.plotly_chart(fig_comp, use_container_width=True)
            st.caption("⚠️ Rentabilidade da carteira calculada vs PM de compra.")

        # ---- Exportação ----
        st.markdown("---")
        st.subheader("⬇️ Exportar Carteira")
        df_export = df.copy()
        df_export["Data exportação"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        csv_bytes = df_export.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="📥 Baixar carteira em CSV",
            data=csv_bytes,
            file_name=f"carteira_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

        # ---- Resumo Fiscal ----
        st.markdown("---")
        st.subheader("🧾 Resumo Fiscal")

        df_fiscal = df[["Ticker", "Tipo", "Qtde", "PM (R$)", "Preço Atual (R$)", "Valor de Mercado (R$)"]].copy()
        df_fiscal["Custo Total (R$)"] = df_fiscal["Qtde"] * df_fiscal["PM (R$)"]
        df_fiscal["Ganho de Capital (R$)"] = df_fiscal["Valor de Mercado (R$)"] - df_fiscal["Custo Total (R$)"]
        df_fiscal["Ganho (%)"] = (
            df_fiscal["Ganho de Capital (R$)"] / df_fiscal["Custo Total (R$)"]
        ).where(df_fiscal["Custo Total (R$)"] > 0, 0) * 100

        def _ir_estimado(row: pd.Series) -> float:
            cfg = ASSET_CONFIG.get(row["Tipo"], ASSET_CONFIG["Ação"])
            ganho = row["Ganho de Capital (R$)"]
            return ganho * cfg["ir_ganho"] if ganho > 0 else 0.0

        df_fiscal["Alíquota IR"] = df_fiscal["Tipo"].map(
            lambda t: f"{ASSET_CONFIG.get(t, ASSET_CONFIG['Ação'])['ir_ganho'] * 100:.0f}%"
        )
        df_fiscal["IR estimado (R$)"] = df_fiscal.apply(_ir_estimado, axis=1)

        col_f1, col_f2, col_f3 = st.columns(3)
        col_f1.metric("💸 Custo total", brl(df_fiscal["Custo Total (R$)"].sum()))
        ganho_total = df_fiscal["Ganho de Capital (R$)"].sum()
        col_f2.metric("📈 Ganho latente", f"{'+' if ganho_total >= 0 else ''}{brl(ganho_total)}")
        col_f3.metric("🏦 IR latente estimado", brl(df_fiscal["IR estimado (R$)"].sum()))

        with st.expander("ℹ️ Sobre alíquotas"):
            st.markdown("""
            - **FIIs:** 20% sobre ganho de capital na venda. Dividendos **isentos** para pessoa física.
            - **Ações:** 15% (swing trade) ou 20% (day trade) sobre ganho de capital. Dividendos **isentos** (Lei 9.249/95).
            - **ETFs:** 15% sobre ganho de capital. Sem isenção mensal.
            - Isenção de IR para vendas de ações ≤ R$ 20.000/mês não está calculada aqui.
            """)

        st.dataframe(
            df_fiscal.drop(columns=["PM (R$)", "Preço Atual (R$)", "Valor de Mercado (R$)"]).style.format({
                "Custo Total (R$)": "R$ {:.2f}",
                "Ganho de Capital (R$)": "R$ {:.2f}",
                "Ganho (%)": "{:+.2f}%",
                "IR estimado (R$)": "R$ {:.2f}",
            }),
            use_container_width=True,
        )

        # ---- Proventos ----
        st.markdown("---")
        st.subheader("💰 Histórico de Proventos / Dividendos")
        proventos = load_proventos()

        with st.expander("➕ Registrar novo provento", expanded=False):
            tickers_carteira = df["Ticker"].tolist()
            col_p1, col_p2, col_p3, col_p4 = st.columns(4)
            with col_p1:
                p_ticker = st.selectbox("Ticker", tickers_carteira, key="p_ticker")
            with col_p2:
                p_data = st.date_input("Data de pagamento", key="p_data")
            with col_p3:
                p_valor = st.number_input("Valor por cota (R$)", min_value=0.0, value=0.0,
                                          step=0.0001, format="%.4f", key="p_valor")
            with col_p4:
                qtd_default = int(df[df["Ticker"] == p_ticker]["Qtde"].values[0]) if p_ticker in df["Ticker"].values else 1
                p_qtd = st.number_input("Qtde de cotas", min_value=1, value=qtd_default, step=1, key="p_qtd")
            if st.button("💾 Salvar provento"):
                if p_valor > 0:
                    add_provento(p_ticker, str(p_data), p_valor, p_qtd)
                    st.success(f"✅ Provento de {brl(p_valor * p_qtd)} registrado para {p_ticker}!")
                    st.rerun()
                else:
                    st.error("❌ Informe um valor por cota maior que zero.")

        if proventos:
            df_prov = pd.DataFrame(proventos).rename(columns={
                "ticker": "Ticker", "data": "Data", "valor_por_cota": "R$/Cota",
                "quantidade": "Qtde", "total": "Total (R$)",
            })
            st.metric("💵 Total recebido em proventos", brl(df_prov["Total (R$)"].sum()))
            df_prov["Mês"] = pd.to_datetime(df_prov["Data"]).dt.to_period("M").astype(str)
            df_mensal = df_prov.groupby("Mês")["Total (R$)"].sum().reset_index().sort_values("Mês")
            fig_prov = go.Figure(go.Bar(
                x=df_mensal["Mês"], y=df_mensal["Total (R$)"],
                marker_color="seagreen",
                text=df_mensal["Total (R$)"].apply(lambda v: f"R$ {v:,.2f}"),
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>R$ %{y:,.2f}<extra></extra>",
            ))
            fig_prov.update_layout(title="Proventos por mês (R$)", height=300,
                                   xaxis=dict(title="Mês"), yaxis=dict(title="R$"),
                                   margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_prov, use_container_width=True)
            st.dataframe(df_prov.drop(columns=["Mês"]).style.format({
                "R$/Cota": "R$ {:.4f}", "Total (R$)": "R$ {:.2f}",
            }), use_container_width=True)
            csv_prov = df_prov.drop(columns=["Mês"]).to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                "📥 Baixar proventos em CSV", data=csv_prov,
                file_name=f"proventos_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv", key="dl_proventos",
            )
        else:
            st.info("📭 Nenhum provento registrado ainda. Use o formulário acima.")

    # ---- Operações ----
    st.markdown("---")
    st.subheader("✏️ Registrar Operação")
    if df.empty:
        return

    tickers = df["Ticker"].tolist()
    col1, col2, col3 = st.columns(3)
    with col1:
        t_sel = st.selectbox("Ticker", tickers)
    with col2:
        qty_add = st.number_input("Quantidade (+ compra / - venda)", value=0, step=1)
    with col3:
        price_op = st.number_input("Preço da operação (R$)", value=0.0, step=0.1, format="%.2f")

    if st.button("🔄 Aplicar operação"):
        if t_sel and qty_add != 0 and price_op > 0:
            p = load_portfolio()
            upsert_position(p, t_sel, int(qty_add), float(price_op))
            clean_positions(p)
            save_portfolio(p)
            st.success("✅ Operação aplicada!")
            st.rerun()
        else:
            st.error("❌ Informe quantidade diferente de zero e preço válido.")
