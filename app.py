import json
import logging
import os
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from dateutil.relativedelta import relativedelta
from brapi import Brapi
from dotenv import load_dotenv

load_dotenv()

# ============= LOGGING =============

os.makedirs("data", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("data/dashboard.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

BRAPI_API_KEY = os.getenv("BRAPI_API_KEY")

if not BRAPI_API_KEY:
    st.error("❌ BRAPI_API_KEY não encontrada! Configure o arquivo .env")
    st.stop()

client = Brapi(api_key=BRAPI_API_KEY)

DATA_DIR = "data"
ATIVOS_CSV = os.path.join(DATA_DIR, "ativos.csv")
PORTFOLIO_JSON = os.path.join(DATA_DIR, "portfolio.json")
PROVENTOS_JSON = os.path.join(DATA_DIR, "proventos.json")

st.set_page_config(page_title="Dashboard Investimentos BR", layout="wide")

# ============= HELPERS =============

def brl(value):
    """Formata valor em reais no padrão brasileiro."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def pct(value):
    """Formata percentual no padrão brasileiro."""
    return f"{value:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")

# ============= TIPOS DE ATIVO =============

# Configuração por tipo: alíquota IR sobre ganho de capital e fonte de DY
ASSET_CONFIG = {
    "FII":  {"ir_ganho": 0.20, "ir_dividendo": 0.00, "label": "FII"},
    "Ação": {"ir_ganho": 0.15, "ir_dividendo": 0.00, "label": "Ação"},
    "ETF":  {"ir_ganho": 0.15, "ir_dividendo": 0.00, "label": "ETF"},
}

# ETFs de índice conhecidos (terminam em 11 mas não são FIIs)
ETFS_BR = {
    "BOVA11","SMAL11","IVVB11","GOLD11","HASH11","XFIX11","SPXI11",
    "DIVO11","FIND11","MATB11","ACWI11","NASD11","FIXA11","GOVE11",
    "BBSD11","IMAB11","IRFM11","LFTE11","MOVA11","TRIG11",
}

# Ações populares do Ibovespa (fallback offline)
ACOES_FALLBACK = [
    "ITUB4","PETR4","VALE3","BBDC4","ABEV3","B3SA3","WEGE3","RENT3",
    "BBAS3","SUZB3","EGIE3","RDOR3","SBSP3","ENEV3","VIVT3","GGBR4",
    "PRIO3","CPLE6","JBSS3","MRVE3","CYRE3","MULT3","LREN3","MGLU3",
    "PETZ3","RECV3","RADL3","TOTS3","EMBR3","BEEF3",
]

# FIIs conhecidos (fallback offline)
FIIS_FALLBACK = [
    "ALZR11","BCFF11","BRCR11","BTLG11","CVBI11","DEVA11","GALG11",
    "GGRC11","HGBS11","HGCR11","HGFF11","HGLG11","HGPO11","HGRE11",
    "HGRU11","HSML11","HTMX11","IRDM11","JSRE11","KNHY11","KNIP11",
    "KNCR11","KNRI11","KNSC11","LVBI11","MALL11","MXRF11","PATL11",
    "PVBI11","RBRF11","RBRP11","RBRY11","RBRR11","RECT11","RECR11",
    "RNGO11","RURA11","RZTR11","SADI11","TGAR11","TRXF11","VGIR11",
    "VIFI11","VILG11","VINO11","VISC11","VRTA11","XPCI11","XPLG11","XPML11",
]

def classify_ticker(ticker):
    """Classifica o tipo do ativo pelo ticker."""
    t = ticker.upper()
    if t in ETFS_BR:
        return "ETF"
    if t.endswith("11"):
        return "FII"
    return "Ação"

# ============= FUNÇÕES DE PREÇO (BRAPI) =============

@st.cache_data(ttl=60 * 30)
def get_last_price(ticker):
    """Busca último preço via Brapi com retry (3 tentativas)."""
    for attempt in range(3):
        try:
            quote = client.quote.retrieve(tickers=ticker)
            if quote.results and len(quote.results) > 0:
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

# ============= FUNÇÕES DE DY / MÉTRICAS (SCRAPING) =============

def _scrape_with_retry(url, headers, label):
    """Executa GET com retry (3 tentativas). Retorna response ou None."""
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=10)
            return r
        except requests.RequestException as e:
            wait = 2 ** attempt
            logger.warning("%s tentativa %d/3: %s. Aguardando %ds...", label, attempt + 1, e, wait)
            if attempt < 2:
                time.sleep(wait)
    logger.error("%s: todas as tentativas falharam", label)
    return None

def _parse_pct(text, low=0, high=100):
    """Extrai float de uma string com '%'. Retorna None se fora do intervalo."""
    try:
        v = float(text.replace("%", "").replace(",", ".").strip())
        if low < v < high:
            return v
    except (ValueError, AttributeError):
        pass
    return None

@st.cache_data(ttl=60 * 60 * 24)
def get_dy_from_fundsexplorer(ticker):
    """Busca DY do FundsExplorer (apenas FIIs)."""
    url = f"https://www.fundsexplorer.com.br/funds/{ticker.lower()}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = _scrape_with_retry(url, headers, f"FundsExplorer/{ticker}")
    if r is None or r.status_code != 200:
        if r:
            logger.warning("FundsExplorer HTTP %d para %s", r.status_code, ticker)
        return None
    soup = BeautifulSoup(r.content, "html.parser")
    for elem in soup.find_all("span", class_="indicator-value"):
        v = _parse_pct(elem.get_text().strip(), 0, 50)
        if v:
            logger.info("DY FundsExplorer: %s = %.2f%%", ticker, v)
            return v / 100
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            for i, cell in enumerate(cells):
                if "dividend yield" in cell.get_text().lower() or " dy" in cell.get_text().lower():
                    if i + 1 < len(cells):
                        v = _parse_pct(cells[i + 1].get_text().strip(), 0, 50)
                        if v:
                            logger.info("DY FundsExplorer (tabela): %s = %.2f%%", ticker, v)
                            return v / 100
    logger.debug("DY não encontrado no FundsExplorer para %s", ticker)
    return None

@st.cache_data(ttl=60 * 60 * 24)
def get_dy_from_statusinvest(ticker, asset_type="FII"):
    """
    Busca DY/DY no StatusInvest.
    URL varia por tipo: FIIs → /fundos-imobiliarios/, Ações → /acoes/, ETFs → /etfs/
    """
    path_map = {"FII": "fundos-imobiliarios", "Ação": "acoes", "ETF": "etfs"}
    path = path_map.get(asset_type, "acoes")
    url = f"https://statusinvest.com.br/{path}/{ticker.lower()}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = _scrape_with_retry(url, headers, f"StatusInvest/{ticker}")
    if r is None or r.status_code != 200:
        if r:
            logger.warning("StatusInvest HTTP %d para %s", r.status_code, ticker)
        return None
    soup = BeautifulSoup(r.content, "html.parser")
    for tag in soup.find_all(["div", "strong"], class_="value"):
        v = _parse_pct(tag.get_text().strip(), 0, 100)
        if v:
            logger.info("DY StatusInvest: %s = %.2f%%", ticker, v)
            return v / 100
    logger.debug("DY não encontrado no StatusInvest para %s", ticker)
    return None

def get_dy_12m_estimate(ticker, asset_type="FII"):
    """Busca DY de múltiplas fontes. FIIs: FundsExplorer → StatusInvest. Ações/ETFs: StatusInvest."""
    if asset_type == "FII":
        dy = get_dy_from_fundsexplorer(ticker)
        if dy is not None and dy > 0:
            return dy
    dy = get_dy_from_statusinvest(ticker, asset_type)
    if dy is not None and dy > 0:
        return dy
    return None

@st.cache_data(ttl=60 * 60 * 6)
def get_benchmark_performance(symbol="IFIX11.SA", period="1y"):
    """Busca histórico de um índice via yfinance (IFIX, IBOV, etc)."""
    fallbacks = {
        "IFIX11.SA": ["IFIX11.SA", "^IFIX"],
        "^BVSP": ["^BVSP"],
    }
    tickers_to_try = fallbacks.get(symbol, [symbol])
    for t in tickers_to_try:
        try:
            hist = yf.Ticker(t).history(period=period)
            if not hist.empty:
                first, last = hist["Close"].iloc[0], hist["Close"].iloc[-1]
                pct_val = (last - first) / first * 100
                logger.info("%s performance (%s): %.2f%%", t, period, pct_val)
                return hist["Close"].reset_index(), pct_val
        except Exception as e:
            logger.warning("Erro ao buscar %s: %s", t, e)
    return None, None

# ============= LISTA DE ATIVOS =============

@st.cache_data(ttl=60 * 30)
def _fetch_ativos_from_brapi(asset_type="fund"):
    """Busca lista de ativos + preço atual via REST Brapi. asset_type: 'fund' ou 'stock'."""
    try:
        url = f"https://brapi.dev/api/quote/list?type={asset_type}&token={BRAPI_API_KEY}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code == 200:
            stocks = r.json().get("stocks", [])
            logger.info("Brapi %s: %d ativos retornados", asset_type, len(stocks))
            return stocks
    except Exception as e:
        logger.warning("Erro ao buscar lista Brapi type=%s: %s", asset_type, e)
    return []

def _build_ativos_list():
    """Monta lista unificada de FIIs, ETFs e Ações com preços."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    ativos = []

    # --- Fundos (FIIs + ETFs) ---
    funds = _fetch_ativos_from_brapi("fund")
    for s in funds:
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

    # --- Ações ---
    stocks = _fetch_ativos_from_brapi("stock")
    for s in stocks:
        ticker = s.get("stock", "").upper()
        # Exclui fundos que aparecem na lista de stocks e BDRs (terminam em 34/32/33)
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

    # Fallback offline se Brapi falhou
    if not ativos:
        logger.warning("Brapi indisponível — usando fallback offline")
        for t in FIIS_FALLBACK:
            ativos.append({"ticker": t, "nome": t, "tipo": "FII", "preco_atual": 0.0, "dy_12m": 0.0, "data_atualizacao": ""})
        for t in ACOES_FALLBACK:
            ativos.append({"ticker": t, "nome": t, "tipo": "Ação", "preco_atual": 0.0, "dy_12m": 0.0, "data_atualizacao": ""})
        for t in ETFS_BR:
            ativos.append({"ticker": t, "nome": t, "tipo": "ETF", "preco_atual": 0.0, "dy_12m": 0.0, "data_atualizacao": ""})

    logger.info("Lista total: %d ativos", len(ativos))
    return ativos

def load_ativos_list():
    """
    Carrega lista de ativos com prioridade:
    1. CSV em disco com menos de 30 min
    2. API Brapi REST (lista + preços)
    3. Fallback offline
    """
    if os.path.exists(ATIVOS_CSV):
        try:
            age_min = (time.time() - os.path.getmtime(ATIVOS_CSV)) / 60
            if age_min < 30:
                df = pd.read_csv(ATIVOS_CSV)
                df["ticker"] = df["ticker"].str.upper().str.strip()
                for col, default in [("preco_atual", 0.0), ("dy_12m", 0.0), ("data_atualizacao", ""), ("tipo", "FII")]:
                    if col not in df.columns:
                        df[col] = default
                logger.info("CSV cache carregado (%.0f min atrás, %d ativos)", age_min, len(df))
                return df
        except Exception as e:
            logger.warning("CSV corrompido, recriando: %s", e)

    ativos = _build_ativos_list()
    df = pd.DataFrame(ativos).sort_values(["tipo", "ticker"]).reset_index(drop=True)
    save_ativos_list(df)
    return df

def save_ativos_list(df):
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(ATIVOS_CSV, index=False, encoding="utf-8")

# ============= PROVENTOS =============

def load_proventos():
    if not os.path.exists(PROVENTOS_JSON):
        return []
    try:
        with open(PROVENTOS_JSON, "r", encoding="utf-8") as f:
            data = json.loads(f.read().strip() or "[]")
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error("Erro ao carregar proventos: %s", e)
        return []

def save_proventos(proventos):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(PROVENTOS_JSON, "w", encoding="utf-8") as f:
            json.dump(proventos, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Erro ao salvar proventos: %s", e)
        st.error(f"❌ Erro ao salvar proventos: {e}")

def add_provento(ticker, data_pagamento, valor_por_cota, quantidade):
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

# ============= PORTFOLIO =============

def load_portfolio():
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

def save_portfolio(data):
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

def upsert_position(portfolio, ticker, quantity, buy_price):
    ticker = ticker.upper()
    for pos in portfolio["positions"]:
        if pos["ticker"] == ticker:
            old_qty = pos["quantity"]
            old_pm = pos["avg_price"]
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
    portfolio["positions"].append({"ticker": ticker, "quantity": quantity, "avg_price": buy_price})

def clean_positions(portfolio):
    portfolio["positions"] = [p for p in portfolio["positions"] if p["quantity"] > 0]

def calc_portfolio_metrics(portfolio):
    """Calcula métricas do portfolio. Busca do CSV primeiro, depois API."""
    df_ativos = load_ativos_list()
    rows = []
    for p in portfolio["positions"]:
        ticker = p["ticker"]
        qty = p["quantity"]
        pm = p["avg_price"]
        asset_type = classify_ticker(ticker)

        cached = df_ativos[df_ativos["ticker"] == ticker]
        if not cached.empty and cached.iloc[0]["preco_atual"] > 0:
            price = float(cached.iloc[0]["preco_atual"])
            dy = float(cached.iloc[0]["dy_12m"])  # já em %
        else:
            price = get_last_price(ticker) or 0.0
            dy_raw = get_dy_12m_estimate(ticker, asset_type)
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

def simulate_projection(
    start_capital, current_monthly_income, monthly_contribution,
    target_monthly_income, yearly_return=0.06, yearly_dividend_growth=0.02,
    yearly_contrib_growth=0.00, max_years=40
):
    r_m = (1 + yearly_return) ** (1 / 12) - 1
    g_div_m = (1 + yearly_dividend_growth) ** (1 / 12) - 1
    g_contrib_m = (1 + yearly_contrib_growth) ** (1 / 12) - 1
    monthly_yield = current_monthly_income / start_capital if start_capital > 0 else 0.007

    today = datetime.today()
    date_points, wealth_points, income_points = [], [], []
    wealth = start_capital
    income = current_monthly_income
    found_months = None

    for month in range(max_years * 12):
        date_points.append(today + relativedelta(months=month))
        wealth_points.append(wealth)
        income_points.append(income)
        if income >= target_monthly_income and found_months is None:
            found_months = month
        monthly_yield *= (1 + g_div_m)
        monthly_contribution *= (1 + g_contrib_m)
        income = wealth * monthly_yield
        wealth = wealth * (1 + r_m) + monthly_contribution

    df = pd.DataFrame({"Data": date_points, "Patrimônio (R$)": wealth_points, "Renda Mensal (R$)": income_points})
    return df, found_months

# ============= STYLING =============

def _highlight_dy(row, dy_min, dy_max):
    dy = row.get("DY/Yield 12m (%)", 0)
    if dy > 0 and dy < dy_min:
        return ["background-color: #ffe5e5"] * len(row)
    if dy >= dy_max:
        return ["background-color: #fff3cd"] * len(row)
    return [""] * len(row)

# ============= PÁGINA: EXPLORAR =============

def page_explore():
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

    display_cols = ["ticker", "nome", "tipo", "preco_atual", "dy_12m", "data_atualizacao"]
    df_display = df_view[display_cols].copy()
    df_display.columns = ["Ticker", "Nome", "Tipo", "Preço Atual (R$)", "DY/Yield 12m (%)", "Última Atualização"]

    st.caption(f"📋 {len(df_view)} ativos encontrados | 💡 'Atualizar DY' busca Dividend Yield via web scraping")
    st.info("📊 **DY/Yield:** FIIs → FundsExplorer + StatusInvest | Ações/ETFs → StatusInvest")

    if st.button("🔄 Atualizar DY dos ativos visíveis"):
        with st.spinner("Buscando DY (pode demorar para muitos ativos)..."):
            total = len(df_view)
            progress_bar = st.progress(0.0)
            data_att = datetime.now().strftime("%Y-%m-%d %H:%M")

            for i, (_, row) in enumerate(df_view.iterrows()):
                ticker = row["ticker"]
                asset_type = row.get("tipo", classify_ticker(ticker))
                dy = get_dy_12m_estimate(ticker, asset_type)
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
        ticker_input = st.text_input("Ticker (ex.: HGLG11, ITUB4, BOVA11)", "")
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

# ============= PÁGINA: CARTEIRA =============

def page_portfolio(dy_min=6.0, dy_max=15.0):
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
        }).apply(_highlight_dy, dy_min=dy_min, dy_max=dy_max, axis=1)
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

        # Alocação por tipo
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
            period_map = {"1 mês": "1mo", "3 meses": "3mo", "6 meses": "6mo", "1 ano": "1y", "2 anos": "2y"}
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
                annotation_text=f"Sua carteira: {100 + carteira_pct:.1f}", annotation_position="right",
            )
            fig_comp.update_layout(title=f"{benchmark_opt} — {period_label} (base 100)",
                                   xaxis=dict(title="Data"), yaxis=dict(title="Base 100"),
                                   height=350, margin=dict(t=40, b=0, l=0, r=10))
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

        def ir_estimado(row):
            cfg = ASSET_CONFIG.get(row["Tipo"], ASSET_CONFIG["Ação"])
            ganho = row["Ganho de Capital (R$)"]
            return ganho * cfg["ir_ganho"] if ganho > 0 else 0.0

        df_fiscal["Alíquota IR"] = df_fiscal["Tipo"].map(
            lambda t: f"{ASSET_CONFIG.get(t, ASSET_CONFIG['Ação'])['ir_ganho']*100:.0f}%"
        )
        df_fiscal["IR estimado (R$)"] = df_fiscal.apply(ir_estimado, axis=1)

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

        st.dataframe(df_fiscal.drop(columns=["PM (R$)", "Preço Atual (R$)", "Valor de Mercado (R$)"]).style.format({
            "Custo Total (R$)": "R$ {:.2f}",
            "Ganho de Capital (R$)": "R$ {:.2f}",
            "Ganho (%)": "{:+.2f}%",
            "IR estimado (R$)": "R$ {:.2f}",
        }), use_container_width=True)

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
            st.download_button("📥 Baixar proventos em CSV", data=csv_prov,
                               file_name=f"proventos_{datetime.now().strftime('%Y%m%d')}.csv",
                               mime="text/csv", key="dl_proventos")
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

# ============= PÁGINA: PROJEÇÕES =============

def page_projection():
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
        monthly_contribution = st.number_input("Aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0, format="%.2f")
        target_income = st.number_input("Meta de renda mensal para IF (R$)", min_value=0.0, value=5000.0, step=100.0, format="%.2f")
        yearly_return = st.number_input("Valorização anual do patrimônio (%)", min_value=-50.0, value=6.0, step=0.5, format="%.2f") / 100.0
    with col[1]:
        st.markdown("##### 📈 Crescimento e Horizonte")
        yearly_div_growth = st.number_input("Crescimento anual dos dividendos (%)", min_value=-50.0, value=2.0, step=0.5, format="%.2f") / 100.0
        yearly_contrib_growth = st.number_input("Crescimento anual do aporte (%)", min_value=-50.0, value=0.0, step=0.5, format="%.2f") / 100.0
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
        fig.add_hline(y=target_income, line_dash="dash", line_color="red",
                      annotation_text=f"Meta: R$ {target_income:,.2f}", annotation_position="right", yref="y2")
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

# ============= MAIN =============

def main():
    st.sidebar.title("📊 Dashboard Investimentos BR")
    st.sidebar.markdown("---")
    page = st.sidebar.radio("🧭 Navegação", ["🔍 Explorar Ativos", "💼 Minha Carteira", "🎯 Projeções"])

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔔 Alertas de DY/Yield")
    dy_min = st.sidebar.number_input("DY mínimo (%)", min_value=0.0, max_value=50.0, value=6.0, step=0.5, format="%.1f",
                                      help="Destaque vermelho para ativos abaixo deste DY")
    dy_max = st.sidebar.number_input("DY máximo (%)", min_value=0.0, max_value=100.0, value=15.0, step=0.5, format="%.1f",
                                      help="Destaque amarelo para DY muito alto (possível risco)")

    st.sidebar.markdown("---")
    st.sidebar.success("✅ **Conectado à Brapi**")
    st.sidebar.info("💡 **Preços:** Brapi REST API")
    st.sidebar.info("📊 **DY:** FundsExplorer + StatusInvest")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📚 Sobre")
    st.sidebar.markdown("Dashboard de investimentos brasileiros: FIIs, Ações e ETFs.")
    st.sidebar.markdown("**Fontes:** [Brapi](https://brapi.dev) · [FundsExplorer](https://fundsexplorer.com.br) · [StatusInvest](https://statusinvest.com.br)")

    if page == "🔍 Explorar Ativos":
        page_explore()
    elif page == "💼 Minha Carteira":
        page_portfolio(dy_min=dy_min, dy_max=dy_max)
    else:
        page_projection()

if __name__ == "__main__":
    main()
