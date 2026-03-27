"""Dashboard Invest BR — entrada principal."""
import logging
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ---- Logging ----
os.makedirs("data", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("data/dashboard.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

# ---- Brapi API key guard ----
if not os.getenv("BRAPI_API_KEY"):
    st.set_page_config(page_title="Dashboard Invest BR", layout="wide")
    st.error("❌ BRAPI_API_KEY não encontrada! Configure o arquivo .env")
    st.stop()

from pages import explore, portfolio, projection  # noqa: E402 (after env check)

st.set_page_config(page_title="Dashboard Invest BR", layout="wide")

# ---- Sidebar ----
st.sidebar.title("📊 Dashboard Invest BR")
st.sidebar.markdown("---")
page = st.sidebar.radio("🧭 Navegação", ["🔍 Explorar Ativos", "💼 Minha Carteira", "🎯 Projeções"])

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔔 Alertas de DY/Yield")
dy_min = st.sidebar.number_input(
    "DY mínimo (%)", min_value=0.0, max_value=50.0, value=6.0, step=0.5, format="%.1f",
    help="Destaque vermelho para ativos abaixo deste DY",
)
dy_max = st.sidebar.number_input(
    "DY máximo (%)", min_value=0.0, max_value=100.0, value=15.0, step=0.5, format="%.1f",
    help="Destaque amarelo para DY muito alto (possível risco)",
)

st.sidebar.markdown("---")
st.sidebar.success("✅ **Conectado à Brapi**")
st.sidebar.info("💡 **Preços:** Brapi REST API")
st.sidebar.info("📊 **DY:** FundsExplorer + StatusInvest")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📚 Sobre")
st.sidebar.markdown("Dashboard de investimentos brasileiros: FIIs, Ações e ETFs.")
st.sidebar.markdown(
    "**Fontes:** [Brapi](https://brapi.dev) · "
    "[FundsExplorer](https://fundsexplorer.com.br) · "
    "[StatusInvest](https://statusinvest.com.br)"
)

# ---- Page routing ----
if page == "🔍 Explorar Ativos":
    explore.render()
elif page == "💼 Minha Carteira":
    portfolio.render(dy_min=dy_min, dy_max=dy_max)
else:
    projection.render()
