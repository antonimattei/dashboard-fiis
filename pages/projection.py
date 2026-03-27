"""Página: Projeções para Independência Financeira."""
import plotly.graph_objects as go
import streamlit as st

from data_layer.portfolio import calc_portfolio_metrics, load_portfolio
from utils import brl, simulate_projection


def render() -> None:
    st.header("🎯 Projeções para Independência Financeira")

    with st.expander("ℹ️ Como funciona o cálculo?", expanded=False):
        st.markdown("""
        ### 📚 Independência Financeira
        **IF** é quando sua renda passiva (dividendos, rendimentos) cobre todas as despesas mensais.

        #### 🧮 Parâmetros:
        - **Patrimônio e renda atuais** — carregados da sua carteira automaticamente
        - **Aporte mensal** — quanto você investe por mês
        - **Meta de renda** — quanto você precisa por mês para viver de renda
        - **Valorização anual** — crescimento esperado dos ativos (histórico IFIX/IBOV: ~6-8%)
        - **Crescimento dos dividendos** — crescimento anual dos rendimentos (média: 2-4%)
        - **Crescimento do aporte** — se você vai aumentar aportes anualmente (ex: reajuste salarial)
        """)

    portfolio = load_portfolio()
    df_pf, totals = calc_portfolio_metrics(portfolio)

    start_capital = totals["Patrimônio (R$)"]
    current_monthly_income = totals["Renda Mensal (R$)"]

    st.write(f"💰 **Patrimônio atual:** {brl(start_capital)}")
    st.write(f"📈 **Renda mensal estimada:** {brl(current_monthly_income)}")
    st.markdown("---")
    st.subheader("⚙️ Configurar Simulação")

    col = st.columns(2)
    with col[0]:
        st.markdown("##### 💵 Aportes e Metas")
        monthly_contribution = st.number_input(
            "Aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0, format="%.2f"
        )
        target_income = st.number_input(
            "Meta de renda mensal para IF (R$)", min_value=0.0, value=5000.0, step=100.0, format="%.2f"
        )
        yearly_return = st.number_input(
            "Valorização anual do patrimônio (%)", min_value=-50.0, value=6.0, step=0.5, format="%.2f"
        ) / 100.0
    with col[1]:
        st.markdown("##### 📈 Crescimento e Horizonte")
        yearly_div_growth = st.number_input(
            "Crescimento anual dos dividendos (%)", min_value=-50.0, value=2.0, step=0.5, format="%.2f"
        ) / 100.0
        yearly_contrib_growth = st.number_input(
            "Crescimento anual do aporte (%)", min_value=-50.0, value=0.0, step=0.5, format="%.2f"
        ) / 100.0
        max_years = st.slider("Horizonte (anos)", min_value=1, max_value=50, value=30)

    if st.button("🚀 Simular", type="primary"):
        with st.spinner("Calculando projeções..."):
            df_sim, months_to_goal = simulate_projection(
                start_capital=start_capital,
                current_monthly_income=current_monthly_income,
                monthly_contribution=monthly_contribution,
                target_monthly_income=target_income,
                yearly_return=yearly_return,
                yearly_dividend_growth=yearly_div_growth,
                yearly_contrib_growth=yearly_contrib_growth,
                max_years=max_years,
            )

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_sim["Data"], y=df_sim["Patrimônio (R$)"], name="Patrimônio (R$)",
            line=dict(color="royalblue", width=3),
            hovertemplate="<b>Data:</b> %{x}<br><b>Patrimônio:</b> R$ %{y:,.2f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=df_sim["Data"], y=df_sim["Renda Mensal (R$)"], name="Renda Mensal (R$)",
            line=dict(color="seagreen", width=3), yaxis="y2",
            hovertemplate="<b>Data:</b> %{x}<br><b>Renda:</b> R$ %{y:,.2f}<extra></extra>",
        ))
        fig.add_hline(
            y=target_income, line_dash="dash", line_color="red",
            annotation_text=f"Meta: R$ {target_income:,.2f}",
            annotation_position="right", yref="y2",
        )
        fig.update_layout(
            title="📊 Projeção de Patrimônio e Renda Mensal",
            xaxis=dict(title="Data"),
            yaxis=dict(title="Patrimônio (R$)", side="left", showgrid=True),
            yaxis2=dict(title="Renda Mensal (R$)", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified", height=600,
        )
        st.plotly_chart(fig, use_container_width=True)

        if months_to_goal is not None:
            years, months = months_to_goal // 12, months_to_goal % 12
            st.success(f"🎉 **Independência financeira estimada em {years} ano(s) e {months} mês(es)!**")
            idx = min(months_to_goal, len(df_sim) - 1)
            col1, col2, col3 = st.columns(3)
            col1.metric("💰 Patrimônio na IF", brl(df_sim["Patrimônio (R$)"].iloc[idx]))
            col2.metric("📈 Renda Mensal na IF", brl(df_sim["Renda Mensal (R$)"].iloc[idx]))
            col3.metric("⏱️ Tempo até IF", f"{years}a {months}m")
        else:
            st.warning("⚠️ Meta não atingida dentro do horizonte selecionado.")
            st.info("💡 **Sugestões:** Aumente o aporte mensal, o horizonte de tempo ou revise a meta.")
            col1, col2 = st.columns(2)
            col1.metric(f"💰 Patrimônio em {max_years} anos", brl(df_sim["Patrimônio (R$)"].iloc[-1]))
            col2.metric(f"📈 Renda em {max_years} anos", brl(df_sim["Renda Mensal (R$)"].iloc[-1]))
