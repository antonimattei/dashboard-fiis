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
IFIX_CSV = os.path.join(DATA_DIR, "ifix_tickers.csv")
PORTFOLIO_JSON = os.path.join(DATA_DIR, "portfolio.json")
PROVENTOS_JSON = os.path.join(DATA_DIR, "proventos.json")

st.set_page_config(page_title="Dashboard FIIs IFIX", layout="wide")

# ============= FUNÇÕES DE API BRAPI =============

@st.cache_data(ttl=60*30)
def get_last_price(ticker):
    """Busca último preço via Brapi com retry (3 tentativas)"""
    for attempt in range(3):
        try:
            quote = client.quote.retrieve(tickers=ticker)
            if quote.results and len(quote.results) > 0:
                result = quote.results[0]
                if hasattr(result, 'regular_market_price') and result.regular_market_price:
                    price = float(result.regular_market_price)
                    logger.info("Preço obtido: %s = R$ %.2f", ticker, price)
                    return price
            logger.warning("Preço não encontrado na resposta Brapi para %s", ticker)
            return None
        except Exception as e:
            wait = 2 ** attempt
            logger.warning("Tentativa %d/3 falhou ao buscar preço de %s: %s. Aguardando %ds...", attempt + 1, ticker, e, wait)
            if attempt < 2:
                time.sleep(wait)
    logger.error("Todas as tentativas falharam ao buscar preço de %s", ticker)
    return None

# ============= FUNÇÕES DE DIVIDENDOS (API ALTERNATIVA GRATUITA FUNDSEXPLORER) =============

@st.cache_data(ttl=60*60*24)  # Cache de 24 horas
def get_dy_from_fundsexplorer(ticker):
    """Busca DY do Funds Explorer (fonte gratuita)"""
    try:
        url = f"https://www.fundsexplorer.com.br/funds/{ticker.lower()}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = None
        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers, timeout=10)
                break
            except requests.RequestException as req_err:
                wait = 2 ** attempt
                logger.warning("FundsExplorer tentativa %d/3 para %s: %s. Aguardando %ds...", attempt + 1, ticker, req_err, wait)
                if attempt < 2:
                    time.sleep(wait)
        if response is None:
            logger.error("FundsExplorer: todas as tentativas falharam para %s", ticker)
            return None

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            dy_elements = soup.find_all('span', class_='indicator-value')

            for elem in dy_elements:
                text = elem.get_text().strip()
                if '%' in text:
                    try:
                        dy_str = text.replace('%', '').replace(',', '.').strip()
                        dy_value = float(dy_str)
                        if 0 < dy_value < 50:
                            logger.info("DY FundsExplorer: %s = %.2f%%", ticker, dy_value)
                            return dy_value / 100
                    except:
                        continue

            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    for i, cell in enumerate(cells):
                        if 'dividend yield' in cell.get_text().lower() or 'dy' in cell.get_text().lower():
                            if i + 1 < len(cells):
                                try:
                                    dy_text = cells[i + 1].get_text().strip()
                                    dy_str = dy_text.replace('%', '').replace(',', '.').strip()
                                    dy_value = float(dy_str)
                                    if 0 < dy_value < 50:
                                        logger.info("DY FundsExplorer (tabela): %s = %.2f%%", ticker, dy_value)
                                        return dy_value / 100
                                except:
                                    continue
        else:
            logger.warning("FundsExplorer retornou HTTP %d para %s", response.status_code, ticker)
    except Exception as e:
        logger.warning("Erro ao buscar DY do FundsExplorer para %s: %s", ticker, e)
    logger.debug("DY não encontrado no FundsExplorer para %s", ticker)
    return None

@st.cache_data(ttl=60*60*24)
def get_dy_from_statusinvest(ticker):
    """Busca DY do Status Invest (fonte gratuita alternativa)"""
    try:
        url = f"https://statusinvest.com.br/fundos-imobiliarios/{ticker.lower()}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = None
        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers, timeout=10)
                break
            except requests.RequestException as req_err:
                wait = 2 ** attempt
                logger.warning("StatusInvest tentativa %d/3 para %s: %s. Aguardando %ds...", attempt + 1, ticker, req_err, wait)
                if attempt < 2:
                    time.sleep(wait)
        if response is None:
            logger.error("StatusInvest: todas as tentativas falharam para %s", ticker)
            return None

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')

            dy_divs = soup.find_all('div', class_='value')
            for div in dy_divs:
                text = div.get_text().strip()
                if '%' in text:
                    try:
                        dy_str = text.replace('%', '').replace(',', '.').strip()
                        dy_value = float(dy_str)
                        if 0 < dy_value < 50:
                            logger.info("DY StatusInvest: %s = %.2f%%", ticker, dy_value)
                            return dy_value / 100
                    except:
                        continue

            strong_tags = soup.find_all('strong', class_='value')
            for tag in strong_tags:
                text = tag.get_text().strip()
                if '%' in text:
                    try:
                        dy_str = text.replace('%', '').replace(',', '.').strip()
                        dy_value = float(dy_str)
                        if 0 < dy_value < 50:
                            logger.info("DY StatusInvest (strong): %s = %.2f%%", ticker, dy_value)
                            return dy_value / 100
                    except:
                        continue
        else:
            logger.warning("StatusInvest retornou HTTP %d para %s", response.status_code, ticker)
    except Exception as e:
        logger.warning("Erro ao buscar DY do StatusInvest para %s: %s", ticker, e)
    logger.debug("DY não encontrado no StatusInvest para %s", ticker)
    return None

def get_dy_12m_estimate(ticker):
    """
    Busca DY de múltiplas fontes gratuitas
    Ordem de prioridade: Funds Explorer -> Status Invest -> Estimativa padrão
    """
    dy = get_dy_from_fundsexplorer(ticker)
    if dy is not None and dy > 0:
        return dy
    
    dy = get_dy_from_statusinvest(ticker)
    if dy is not None and dy > 0:
        return dy
    
    # Se não conseguir de nenhuma fonte, retorna None
    return None

@st.cache_data(ttl=60*60*6)  # Cache de 6 horas
def get_ifix_performance(period="1y"):
    """Busca cotação histórica do IFIX via yfinance para comparativo"""
    try:
        ticker_ifix = yf.Ticker("IFIX11.SA")
        hist = ticker_ifix.history(period=period)
        if hist.empty:
            logger.warning("IFIX11.SA sem dados no yfinance, tentando ^IFIX")
            ticker_ifix = yf.Ticker("^IFIX")
            hist = ticker_ifix.history(period=period)
        if not hist.empty:
            first = hist["Close"].iloc[0]
            last = hist["Close"].iloc[-1]
            pct = (last - first) / first * 100
            logger.info("IFIX performance (%s): %.2f%%", period, pct)
            return hist["Close"].reset_index(), pct
    except Exception as e:
        logger.warning("Erro ao buscar performance do IFIX: %s", e)
    return None, None


def get_dividends_12m(ticker):
    """Calcula dividendos anuais baseado no DY e preço atual"""
    price = get_last_price(ticker)
    dy = get_dy_12m_estimate(ticker)
    
    if price and dy and price > 0 and dy > 0:
        return price * dy
    
    return 0.0

# ============= LISTA DE FIIs CONHECIDOS (FALLBACK) =============

FIIS_FALLBACK = [
    "ALZR11","BCFF11","BRCR11","BTLG11","CVBI11","DEVA11","GALG11",
    "GGRC11","HGBS11","HGCR11","HGFF11","HGLG11","HGPO11","HGRE11",
    "HGRU11","HSML11","HTMX11","IRDM11","JSRE11","KNHY11","KNIP11",
    "KNCR11","KNRI11","KNSC11","LVBI11","MALL11","MXRF11","PATL11",
    "PVBI11","RBRF11","RBRP11","RBRY11","RBRR11","RECT11","RECR11",
    "RNGO11","RURA11","RZTR11","SADI11","TGAR11","TRXF11","VGIR11",
    "VIFI11","VILG11","VINO11","VISC11","VRTA11","XPCI11","XPLG11","XPML11",
]

# ============= FUNÇÕES DE PORTFOLIO =============

@st.cache_data(ttl=60*60*12)  # Cache de 12 horas
def _fetch_ifix_from_brapi():
    """Busca lista de FIIs diretamente da Brapi."""
    try:
        response = client.quote.list()
        fiis = []
        for stock in response.stocks:
            ticker = stock.stock
            if ticker.endswith("11"):
                fiis.append({
                    "ticker": ticker.upper(),
                    "nome": getattr(stock, "name", ticker),
                    "tipo": getattr(stock, "type", "FII"),
                })
        if fiis:
            logger.info("Lista Brapi: %d FIIs encontrados", len(fiis))
            return fiis
    except Exception as e:
        logger.warning("Erro ao buscar lista da Brapi: %s", e)
    return None


def load_ifix_list():
    """
    Carrega lista de FIIs com prioridade:
    1. CSV em disco (cache local com preços/DY já preenchidos)
    2. API Brapi (busca ao vivo)
    3. Lista hardcoded (fallback offline)
    """
    # 1. Tenta CSV local
    if os.path.exists(IFIX_CSV):
        try:
            df = pd.read_csv(IFIX_CSV)
            df["ticker"] = df["ticker"].str.upper().str.strip()
            if "preco_atual" not in df.columns:
                df["preco_atual"] = 0.0
            if "dy_12m" not in df.columns:
                df["dy_12m"] = 0.0
            if "data_atualizacao" not in df.columns:
                df["data_atualizacao"] = ""
            return df
        except Exception as e:
            logger.warning("CSV corrompido, recriando: %s", e)

    # 2. Tenta Brapi
    fiis = _fetch_ifix_from_brapi()

    # 3. Fallback hardcoded
    if not fiis:
        logger.warning("Usando lista hardcoded de FIIs (fallback)")
        fiis = [{"ticker": t, "nome": t, "tipo": "FII"} for t in FIIS_FALLBACK]

    df = pd.DataFrame(fiis).sort_values("ticker").reset_index(drop=True)
    df["preco_atual"] = 0.0
    df["dy_12m"] = 0.0
    df["data_atualizacao"] = ""

    # Persiste o CSV para próximas execuções
    save_ifix_list(df)
    return df


def save_ifix_list(df):
    """Salva lista de FIIs no CSV com preços e DY atualizados"""
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(IFIX_CSV, index=False, encoding='utf-8')

# ============= FUNÇÕES DE PROVENTOS =============

def load_proventos():
    """Carrega histórico de proventos registrados manualmente"""
    if not os.path.exists(PROVENTOS_JSON):
        return []
    try:
        with open(PROVENTOS_JSON, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            data = json.loads(content)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error("Erro ao carregar proventos: %s", e)
        return []

def save_proventos(proventos):
    """Salva histórico de proventos"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(PROVENTOS_JSON, "w", encoding="utf-8") as f:
            json.dump(proventos, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Erro ao salvar proventos: %s", e)
        st.error(f"❌ Erro ao salvar proventos: {e}")

def add_provento(ticker, data_pagamento, valor_por_cota, quantidade):
    """Adiciona um registro de provento recebido"""
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

def load_portfolio():
    """Carrega portfolio com tratamento de erros"""
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
            
            if "positions" not in data:
                data["positions"] = []
            
            return data
            
    except json.JSONDecodeError as e:
        logger.error("portfolio.json corrompido: %s", e)
        st.error(f"⚠️ Erro ao ler portfolio.json: {str(e)}")
        st.info("🔄 Criando novo portfolio...")
        new_portfolio = {"positions": []}
        save_portfolio(new_portfolio)
        return new_portfolio
    except Exception as e:
        logger.error("Erro inesperado ao carregar portfolio: %s", e)
        st.error(f"❌ Erro inesperado: {str(e)}")
        return {"positions": []}

def save_portfolio(data):
    """Salva portfolio com validação"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)

        if not isinstance(data, dict):
            data = {"positions": []}
        
        if "positions" not in data:
            data["positions"] = []
        
        with open(PORTFOLIO_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.error("Erro ao salvar portfolio: %s", e)
        st.error(f"❌ Erro ao salvar portfolio: {str(e)}")

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
                # Compra: recalcula preço médio ponderado
                pos["avg_price"] = (old_qty * old_pm + quantity * buy_price) / new_qty
                pos["quantity"] = new_qty
            else:
                # Venda parcial: PM não se altera
                pos["quantity"] = new_qty
            return
    portfolio["positions"].append({"ticker": ticker, "quantity": quantity, "avg_price": buy_price})

def clean_positions(portfolio):
    portfolio["positions"] = [p for p in portfolio["positions"] if p["quantity"] > 0]

def calc_portfolio_metrics(portfolio):
    """Calcula métricas do portfolio usando dados salvos no CSV quando disponível"""
    df_ifix = load_ifix_list()
    rows = []
    
    for p in portfolio["positions"]:
        ticker = p["ticker"]
        qty = p["quantity"]
        pm = p["avg_price"]
        
        # Tentar buscar do CSV primeiro
        ticker_data = df_ifix[df_ifix["ticker"] == ticker]
        
        if not ticker_data.empty and ticker_data.iloc[0]["preco_atual"] > 0:
            price = ticker_data.iloc[0]["preco_atual"]
            dy = ticker_data.iloc[0]["dy_12m"]
        else:
            # Se não tiver no CSV, buscar da API
            price = get_last_price(ticker)
            dy_raw = get_dy_12m_estimate(ticker)
            dy = (dy_raw * 100) if dy_raw is not None else 0.0
            
        if price is None:
            price = 0.0
        if dy is None:
            dy = 0.0
            
        market = qty * price
        change = (price - pm) / pm if pm else 0.0
        monthly_income = (dy / 100 * price / 12.0) * qty
        
        rows.append({
            "Ticker": ticker,
            "Qtde": qty,
            "PM": pm,
            "Preço Atual": price,
            "Variação (%)": change * 100,
            "DY 12m (%)": dy,
            "Valor de Mercado": market,
            "Renda Mensal Estimada": monthly_income
        })
    
    df = pd.DataFrame(rows)
    totals = {}
    if not df.empty:
        totals["Patrimônio (R$)"] = df["Valor de Mercado"].sum()
        totals["Renda Mensal (R$)"] = df["Renda Mensal Estimada"].sum()
        if totals["Patrimônio (R$)"] > 0:
            totals["DY Médio (%)"] = (totals["Renda Mensal (R$)"] * 12) / totals["Patrimônio (R$)"] * 100
        else:
            totals["DY Médio (%)"] = 0.0
    else:
        totals = {"Patrimônio (R$)": 0.0, "Renda Mensal (R$)": 0.0, "DY Médio (%)": 0.0}
    return df, totals

def simulate_projection(
    start_capital,
    current_monthly_income,
    monthly_contribution,
    target_monthly_income,
    yearly_return=0.06,
    yearly_dividend_growth=0.02,
    yearly_contrib_growth=0.00,
    max_years=40
):
    r_m = (1 + yearly_return) ** (1/12) - 1
    g_div_m = (1 + yearly_dividend_growth) ** (1/12) - 1
    g_contrib_m = (1 + yearly_contrib_growth) ** (1/12) - 1

    if start_capital > 0:
        monthly_yield = current_monthly_income / start_capital
    else:
        monthly_yield = 0.007

    date_points = []
    wealth_points = []
    income_points = []

    today = datetime.today()
    month = 0
    wealth = start_capital
    income = current_monthly_income

    found_months = None

    while month < max_years * 12:
        date_points.append(today + relativedelta(months=month))
        wealth_points.append(wealth)
        income_points.append(income)

        if income >= target_monthly_income and found_months is None:
            found_months = month

        monthly_yield = monthly_yield * (1 + g_div_m)
        monthly_contribution = monthly_contribution * (1 + g_contrib_m)
        income = wealth * monthly_yield
        wealth = wealth * (1 + r_m) + monthly_contribution

        month += 1

    df = pd.DataFrame({
        "Data": date_points,
        "Patrimônio (R$)": wealth_points,
        "Renda Mensal (R$)": income_points
    })
    return df, found_months

# ============= PÁGINAS =============

def page_explore():
    st.header("🔍 Explorar FIIs do IFIX")
    df_ifix = load_ifix_list()

    search = st.text_input("Buscar por ticker ou nome", "").strip().upper()
    df_view = df_ifix.copy()
    if search:
        df_view = df_view[df_view.apply(lambda r: search in r["ticker"].upper() or search in str(r.get("nome", "")).upper(), axis=1)]

    # Preparar visualização
    display_cols = ["ticker", "nome", "tipo"]
    if "preco_atual" in df_view.columns:
        display_cols.append("preco_atual")
    if "dy_12m" in df_view.columns:
        display_cols.append("dy_12m")
    if "data_atualizacao" in df_view.columns:
        display_cols.append("data_atualizacao")
    
    df_display = df_view[display_cols].copy()
    df_display.columns = ["Ticker", "Nome", "Tipo", "Preço Atual (R$)", "DY 12m (%)", "Última Atualização"]
    
    st.caption("💡 Clique em 'Atualizar métricas' para buscar preço e DY dos tickers visíveis e salvar no CSV.")
    st.info("📊 **DY obtido de:** Funds Explorer e Status Invest (fontes gratuitas)")
    
    if st.button("🔄 Atualizar métricas"):
        with st.spinner("Buscando dados do mercado (Brapi + Funds Explorer + Status Invest)..."):
            progress_bar = st.progress(0)
            total = len(df_view)
            data_atualizacao = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            for idx, row in df_view.iterrows():
                ticker = row["ticker"]
                
                # Buscar preço
                price = get_last_price(ticker)
                df_ifix.loc[df_ifix["ticker"] == ticker, "preco_atual"] = price if price else 0.0
                
                # Buscar DY
                dy = get_dy_12m_estimate(ticker)
                df_ifix.loc[df_ifix["ticker"] == ticker, "dy_12m"] = (dy * 100) if dy is not None else 0.0
                
                # Atualizar data
                df_ifix.loc[df_ifix["ticker"] == ticker, "data_atualizacao"] = data_atualizacao
                
                progress_bar.progress((idx + 1) / total)
            
            # Salvar CSV atualizado
            save_ifix_list(df_ifix)
            
            progress_bar.empty()
            st.success(f"✅ Métricas atualizadas e salvas no CSV em {data_atualizacao}!")
            st.rerun()

    st.dataframe(df_display, use_container_width=True)

    st.subheader("➕ Adicionar posição à carteira")
    col1, col2, col3 = st.columns(3)
    with col1:
        ticker = st.text_input("Ticker (ex.: HGLG11)", "")
    with col2:
        qty = st.number_input("Quantidade", min_value=1, value=10, step=1)
    with col3:
        buy_price = st.number_input("Preço de compra (R$)", min_value=0.0, value=100.0, step=0.1, format="%.2f")

    if st.button("✅ Adicionar"):
        if ticker:
            portfolio = load_portfolio()
            upsert_position(portfolio, ticker.upper(), qty, buy_price)
            clean_positions(portfolio)
            save_portfolio(portfolio)
            st.success(f"✅ {qty} cotas de {ticker.upper()} adicionadas à carteira!")
            st.balloons()
            st.rerun()
        else:
            st.error("❌ Informe um ticker válido.")

def _highlight_dy(row, dy_min, dy_max):
    """Aplica cor de fundo na linha conforme o DY."""
    dy = row.get("DY 12m (%)", 0)
    if dy > 0 and dy < dy_min:
        return ["background-color: #ffe5e5"] * len(row)
    if dy >= dy_max:
        return ["background-color: #fff3cd"] * len(row)
    return [""] * len(row)


def page_portfolio(dy_min=6.0, dy_max=15.0):
    st.header("💼 Minha Carteira")
    portfolio = load_portfolio()

    with st.spinner("Carregando dados da carteira..."):
        df, totals = calc_portfolio_metrics(portfolio)

    col1, col2, col3 = st.columns(3)
    col1.metric("💰 Patrimônio", f"R$ {totals['Patrimônio (R$)']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    col2.metric("📈 Renda Mensal Est.", f"R$ {totals['Renda Mensal (R$)']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    col3.metric("📊 DY Médio", f"{totals['DY Médio (%)']:,.2f}%".replace(",", "X").replace(".", ",").replace("X", "."))

    if not df.empty:
        # Alertas de DY
        alertas_baixo = df[df["DY 12m (%)"].between(0.01, dy_min, inclusive="left")]
        alertas_alto = df[df["DY 12m (%)"] >= dy_max]
        if not alertas_baixo.empty:
            tickers_baixo = ", ".join(alertas_baixo["Ticker"].tolist())
            st.warning(f"⚠️ DY abaixo de {dy_min:.1f}%: **{tickers_baixo}**")
        if not alertas_alto.empty:
            tickers_alto = ", ".join(alertas_alto["Ticker"].tolist())
            st.info(f"🟡 DY acima de {dy_max:.1f}% (atenção ao risco): **{tickers_alto}**")

        styled = df.style.format({
            "PM": "R$ {:.2f}",
            "Preço Atual": "R$ {:.2f}",
            "Variação (%)": "{:.2f}%",
            "DY 12m (%)": "{:.2f}%",
            "Valor de Mercado": "R$ {:.2f}",
            "Renda Mensal Estimada": "R$ {:.2f}"
        }).apply(_highlight_dy, dy_min=dy_min, dy_max=dy_max, axis=1)
        st.dataframe(styled, use_container_width=True)
        st.caption(f"🔴 DY < {dy_min:.1f}%  |  🟡 DY ≥ {dy_max:.1f}%  (thresholds configuráveis na barra lateral)")

        st.markdown("---")
        st.subheader("📊 Alocação da Carteira")
        col_pie, col_bar = st.columns(2)

        with col_pie:
            fig_pie = go.Figure(go.Pie(
                labels=df["Ticker"],
                values=df["Valor de Mercado"],
                hole=0.4,
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}<extra></extra>",
            ))
            fig_pie.update_layout(
                title="Participação por FII (%)",
                showlegend=False,
                height=380,
                margin=dict(t=40, b=0, l=0, r=0),
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_bar:
            df_sorted = df.sort_values("Valor de Mercado", ascending=True)
            fig_bar = go.Figure(go.Bar(
                x=df_sorted["Valor de Mercado"],
                y=df_sorted["Ticker"],
                orientation="h",
                text=df_sorted["Valor de Mercado"].apply(lambda v: f"R$ {v:,.0f}"),
                textposition="outside",
                marker_color="royalblue",
                hovertemplate="<b>%{y}</b><br>R$ %{x:,.2f}<extra></extra>",
            ))
            fig_bar.update_layout(
                title="Valor de Mercado por FII (R$)",
                xaxis=dict(title="R$"),
                yaxis=dict(title=""),
                height=380,
                margin=dict(t=40, b=0, l=0, r=10),
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        # ---- Comparativo com IFIX ----
        st.markdown("---")
        st.subheader("📈 Comparativo vs IFIX")

        period_map = {"1 mês": "1mo", "3 meses": "3mo", "6 meses": "6mo", "1 ano": "1y", "2 anos": "2y"}
        period_label = st.selectbox("Período", list(period_map.keys()), index=3, key="ifix_period")
        period_code = period_map[period_label]

        with st.spinner("Buscando dados do IFIX..."):
            hist_ifix, ifix_pct = get_ifix_performance(period_code)

        # Rentabilidade da carteira no período: usa variação média ponderada (Preço Atual vs PM)
        total_mercado = df["Valor de Mercado"].sum()
        if total_mercado > 0:
            df["_peso"] = df["Valor de Mercado"] / total_mercado
            carteira_pct = (df["Variação (%)"] * df["_peso"]).sum()
        else:
            carteira_pct = 0.0

        col_c1, col_c2, col_c3 = st.columns(3)
        col_c1.metric("📊 Sua carteira (vs PM)", f"{carteira_pct:+.2f}%")
        if ifix_pct is not None:
            diff = carteira_pct - ifix_pct
            col_c2.metric(f"📉 IFIX ({period_label})", f"{ifix_pct:+.2f}%")
            col_c3.metric("⚖️ Alpha (carteira − IFIX)", f"{diff:+.2f}%", delta_color="normal")
        else:
            col_c2.metric(f"📉 IFIX ({period_label})", "Indisponível")
            col_c3.metric("⚖️ Alpha", "—")

        if hist_ifix is not None and not hist_ifix.empty:
            hist_ifix_norm = hist_ifix.copy()
            hist_ifix_norm["IFIX (base 100)"] = hist_ifix_norm["Close"] / hist_ifix_norm["Close"].iloc[0] * 100

            fig_comp = go.Figure()
            fig_comp.add_trace(go.Scatter(
                x=hist_ifix_norm["Date"],
                y=hist_ifix_norm["IFIX (base 100)"],
                name="IFIX",
                line=dict(color="darkorange", width=2),
                hovertemplate="<b>IFIX</b><br>%{x}<br>Base 100: %{y:.1f}<extra></extra>",
            ))
            # Linha da carteira como valor constante (variação acumulada desde PM)
            if len(hist_ifix_norm) >= 2:
                carteira_base100 = 100 + carteira_pct
                fig_comp.add_hline(
                    y=carteira_base100,
                    line_dash="dash",
                    line_color="royalblue",
                    annotation_text=f"Sua carteira: {carteira_base100:.1f}",
                    annotation_position="right",
                )
            fig_comp.update_layout(
                title=f"IFIX — últimos {period_label} (base 100)",
                xaxis=dict(title="Data"),
                yaxis=dict(title="Base 100"),
                height=350,
                margin=dict(t=40, b=0, l=0, r=10),
            )
            st.plotly_chart(fig_comp, use_container_width=True)
            st.caption("⚠️ Rentabilidade da carteira calculada com base no preço médio de compra (PM). IFIX via yfinance.")

        # ---- Exportação CSV ----
        st.markdown("---")
        st.subheader("⬇️ Exportar Carteira")

        df_export = df.drop(columns=["_peso"], errors="ignore").copy()
        df_export["Data exportação"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        csv_bytes = df_export.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="📥 Baixar carteira em CSV",
            data=csv_bytes,
            file_name=f"carteira_fiis_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

        # ---- Resumo Fiscal ----
        st.markdown("---")
        st.subheader("🧾 Resumo Fiscal")
        st.caption("FIIs são isentos de IR sobre dividendos para pessoas físicas. O IR incide apenas sobre ganho de capital na venda de cotas.")

        df_fiscal = df[["Ticker", "Qtde", "PM", "Preço Atual", "Valor de Mercado"]].copy()
        df_fiscal["Custo Total (R$)"] = df_fiscal["Qtde"] * df_fiscal["PM"]
        df_fiscal["Ganho de Capital (R$)"] = df_fiscal["Valor de Mercado"] - df_fiscal["Custo Total (R$)"]
        df_fiscal["Ganho (%)"] = (df_fiscal["Ganho de Capital (R$)"] / df_fiscal["Custo Total (R$)"]).where(
            df_fiscal["Custo Total (R$)"] > 0, 0
        ) * 100
        df_fiscal["IR estimado (20%)"] = df_fiscal["Ganho de Capital (R$)"].apply(lambda x: x * 0.20 if x > 0 else 0.0)

        total_custo = df_fiscal["Custo Total (R$)"].sum()
        total_ganho = df_fiscal["Ganho de Capital (R$)"].sum()
        total_ir = df_fiscal["IR estimado (20%)"].sum()

        col_f1, col_f2, col_f3 = st.columns(3)
        col_f1.metric("💸 Custo total", f"R$ {total_custo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        sinal = "+" if total_ganho >= 0 else ""
        col_f2.metric("📈 Ganho de capital latente", f"{sinal}R$ {total_ganho:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        col_f3.metric("🏦 IR latente (20% sobre ganho)", f"R$ {total_ir:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

        st.dataframe(df_fiscal.drop(columns=["PM", "Preço Atual", "Valor de Mercado"]).style.format({
            "Custo Total (R$)": "R$ {:.2f}",
            "Ganho de Capital (R$)": "R$ {:.2f}",
            "Ganho (%)": "{:.2f}%",
            "IR estimado (20%)": "R$ {:.2f}",
        }).applymap(lambda v: "color: green" if isinstance(v, (int, float)) and v > 0 else (
            "color: red" if isinstance(v, (int, float)) and v < 0 else ""
        ), subset=["Ganho de Capital (R$)", "Ganho (%)"]), use_container_width=True)

        # ---- Histórico de Proventos ----
        st.markdown("---")
        st.subheader("💰 Histórico de Proventos Recebidos")

        proventos = load_proventos()

        with st.expander("➕ Registrar novo provento", expanded=False):
            tickers_carteira = df["Ticker"].tolist()
            col_p1, col_p2, col_p3, col_p4 = st.columns(4)
            with col_p1:
                p_ticker = st.selectbox("Ticker", tickers_carteira, key="p_ticker")
            with col_p2:
                p_data = st.date_input("Data de pagamento", key="p_data")
            with col_p3:
                p_valor = st.number_input("Valor por cota (R$)", min_value=0.0, value=0.0, step=0.01, format="%.4f", key="p_valor")
            with col_p4:
                p_qtd_default = int(df[df["Ticker"] == p_ticker]["Qtde"].values[0]) if p_ticker in df["Ticker"].values else 1
                p_qtd = st.number_input("Quantidade de cotas", min_value=1, value=p_qtd_default, step=1, key="p_qtd")
            if st.button("💾 Salvar provento"):
                if p_valor > 0:
                    add_provento(p_ticker, str(p_data), p_valor, p_qtd)
                    st.success(f"✅ Provento de R$ {p_valor * p_qtd:.2f} registrado para {p_ticker}!")
                    st.rerun()
                else:
                    st.error("❌ Informe um valor por cota maior que zero.")

        if proventos:
            df_prov = pd.DataFrame(proventos)
            df_prov = df_prov.rename(columns={
                "ticker": "Ticker", "data": "Data", "valor_por_cota": "R$/Cota",
                "quantidade": "Qtde", "total": "Total (R$)"
            })
            total_proventos = df_prov["Total (R$)"].sum()
            st.metric("💵 Total recebido em proventos", f"R$ {total_proventos:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

            # Gráfico de proventos por mês
            df_prov["Mês"] = pd.to_datetime(df_prov["Data"]).dt.to_period("M").astype(str)
            df_mensal = df_prov.groupby("Mês")["Total (R$)"].sum().reset_index().sort_values("Mês")
            fig_prov = go.Figure(go.Bar(
                x=df_mensal["Mês"],
                y=df_mensal["Total (R$)"],
                marker_color="seagreen",
                text=df_mensal["Total (R$)"].apply(lambda v: f"R$ {v:,.2f}"),
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>R$ %{y:,.2f}<extra></extra>",
            ))
            fig_prov.update_layout(
                title="Proventos recebidos por mês (R$)",
                xaxis=dict(title="Mês"),
                yaxis=dict(title="R$"),
                height=300,
                margin=dict(t=40, b=0, l=0, r=0),
            )
            st.plotly_chart(fig_prov, use_container_width=True)

            st.dataframe(df_prov.style.format({
                "R$/Cota": "R$ {:.4f}",
                "Total (R$)": "R$ {:.2f}",
            }), use_container_width=True)

            # Exportar proventos
            csv_prov = df_prov.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="📥 Baixar proventos em CSV",
                data=csv_prov,
                file_name=f"proventos_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                key="dl_proventos",
            )
        else:
            st.info("📭 Nenhum provento registrado ainda. Use o formulário acima para registrar.")

    else:
        st.info("📭 Sua carteira está vazia. Adicione FIIs na aba 'Explorar FIIs'.")

    st.subheader("✏️ Remover/Atualizar posição")
    if df.empty:
        return

    tickers = df["Ticker"].tolist()
    col1, col2, col3 = st.columns(3)
    with col1:
        t_sel = st.selectbox("Ticker", tickers)
    with col2:
        qty_add = st.number_input("Adicionar quantidade (positivo compra, negativo venda)", value=0, step=1)
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
            st.error("❌ Informe ticker, quantidade diferente de zero e preço válido.")

def page_projection():
    st.header("🎯 Projeções para Independência Financeira")
    
    # Explicação sobre Independência Financeira
    with st.expander("ℹ️ O que é Independência Financeira?", expanded=False):
        st.markdown("""
        ### 📚 Entenda a Independência Financeira
        
        **Independência Financeira (IF)** é quando sua renda passiva (dividendos, aluguéis, etc.) 
        cobre todas as suas despesas mensais, permitindo que você não precise trabalhar para viver.
        
        #### 🧮 Como funciona o cálculo:
        
        1. **💰 Patrimônio Atual**: Quanto você tem investido hoje em FIIs
        2. **📈 Renda Mensal Atual**: Quanto seus FIIs pagam de dividendos por mês hoje
        3. **💵 Aporte Mensal**: Quanto você vai investir todo mês
        4. **🎯 Meta de Renda Mensal**: Quanto você precisa receber por mês para ser independente
        
        #### 📊 Parâmetros de Crescimento:
        
        - **Valorização do Patrimônio**: Quanto seus FIIs vão valorizar por ano (média histórica: 6%)
        - **Crescimento dos Dividendos**: Quanto os dividendos vão aumentar por ano (média: 2-4%)
        - **Crescimento do Aporte**: Se você planeja aumentar seus aportes anualmente (ex: acompanhar inflação)
        
        #### 💡 Exemplo Prático:
        
        Se você tem R$ 50.000 investidos, recebe R$ 400/mês de dividendos, aporta R$ 1.000/mês 
        e precisa de R$ 5.000/mês para viver, o simulador calcula em quanto tempo você chegará lá!
        """)

    portfolio = load_portfolio()
    df_pf, totals = calc_portfolio_metrics(portfolio)

    start_capital = totals["Patrimônio (R$)"]
    current_monthly_income = totals["Renda Mensal (R$)"]

    st.write(f"💰 **Patrimônio atual:** R$ {start_capital:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    st.write(f"📈 **Renda mensal atual estimada:** R$ {current_monthly_income:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    st.markdown("---")
    st.subheader("⚙️ Configurar Simulação")
    
    col = st.columns(2)
    with col[0]:
        st.markdown("##### 💵 Aportes e Metas")
        monthly_contribution = st.number_input(
            "💵 Aporte mensal (R$)", 
            min_value=0.0, 
            value=1000.0, 
            step=100.0, 
            format="%.2f",
            help="Quanto você vai investir todo mês em FIIs"
        )
        target_income = st.number_input(
            "🎯 Meta de renda mensal para IF (R$)", 
            min_value=0.0, 
            value=5000.0, 
            step=100.0, 
            format="%.2f",
            help="Quanto você precisa receber por mês para cobrir suas despesas e ser independente financeiramente"
        )
        yearly_return = st.number_input(
            "📊 Valorização anual do patrimônio (%)", 
            min_value=-50.0, 
            value=6.0, 
            step=0.5, 
            format="%.2f",
            help="Quanto você espera que seus FIIs valorizem por ano. Média histórica do IFIX: 6% ao ano"
        ) / 100.0
        
    with col[1]:
        st.markdown("##### 📈 Crescimento e Horizonte")
        yearly_div_growth = st.number_input(
            "📈 Crescimento anual dos dividendos (%)", 
            min_value=-50.0, 
            value=2.0, 
            step=0.5, 
            format="%.2f",
            help="Quanto você espera que os dividendos cresçam por ano. Média histórica: 2-4% ao ano"
        ) / 100.0
        yearly_contrib_growth = st.number_input(
            "💰 Crescimento anual do aporte (%)", 
            min_value=-50.0, 
            value=0.0, 
            step=0.5, 
            format="%.2f",
            help="Se você planeja aumentar seus aportes anualmente (ex: 5% para acompanhar aumentos salariais)"
        ) / 100.0
        max_years = st.slider(
            "⏳ Horizonte (anos)", 
            min_value=1, 
            max_value=50, 
            value=30,
            help="Por quantos anos você quer simular o crescimento do seu patrimônio"
        )

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
                max_years=max_years
            )

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_sim["Data"], 
                y=df_sim["Patrimônio (R$)"], 
                name="Patrimônio (R$)", 
                line=dict(color="royalblue", width=3),
                hovertemplate='<b>Data:</b> %{x}<br><b>Patrimônio:</b> R$ %{y:,.2f}<extra></extra>'
            ))
            fig.add_trace(go.Scatter(
                x=df_sim["Data"], 
                y=df_sim["Renda Mensal (R$)"], 
                name="Renda Mensal (R$)", 
                line=dict(color="seagreen", width=3), 
                yaxis="y2",
                hovertemplate='<b>Data:</b> %{x}<br><b>Renda:</b> R$ %{y:,.2f}<extra></extra>'
            ))
            
            # Adicionar linha da meta
            fig.add_hline(
                y=target_income, 
                line_dash="dash", 
                line_color="red", 
                annotation_text=f"Meta: R$ {target_income:,.2f}",
                annotation_position="right",
                yref="y2"
            )

            fig.update_layout(
                title="📊 Projeção de Patrimônio e Renda Mensal",
                xaxis=dict(title="Data"),
                yaxis=dict(title="Patrimônio (R$)", side="left", showgrid=True),
                yaxis2=dict(title="Renda Mensal (R$)", overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode='x unified',
                height=600
            )
            st.plotly_chart(fig, use_container_width=True)

            if months_to_goal is not None:
                years = months_to_goal // 12
                months = months_to_goal % 12
                st.success(f"🎉 **Independência financeira estimada em {years} ano(s) e {months} mês(es)**!")
                st.info(f"📅 Você atingirá sua meta de R$ {target_income:,.2f}/mês de renda passiva!".replace(",", "X").replace(".", ",").replace("X", "."))
                
                # Mostrar resumo final
                final_wealth = df_sim["Patrimônio (R$)"].iloc[-1] if months_to_goal < len(df_sim) else df_sim["Patrimônio (R$)"].iloc[months_to_goal]
                final_income = df_sim["Renda Mensal (R$)"].iloc[-1] if months_to_goal < len(df_sim) else df_sim["Renda Mensal (R$)"].iloc[months_to_goal]
                
                col1, col2, col3 = st.columns(3)
                col1.metric("💰 Patrimônio Final", f"R$ {final_wealth:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                col2.metric("📈 Renda Mensal Final", f"R$ {final_income:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                col3.metric("⏱️ Tempo até IF", f"{years}a {months}m")
                
            else:
                st.warning("⚠️ Meta não atingida dentro do horizonte selecionado.")
                st.info("💡 **Sugestões:**\n- Aumente o aporte mensal\n- Aumente o horizonte de tempo\n- Revise sua meta de renda mensal")
                
                # Mostrar onde chegaria
                final_wealth = df_sim["Patrimônio (R$)"].iloc[-1]
                final_income = df_sim["Renda Mensal (R$)"].iloc[-1]
                
                col1, col2 = st.columns(2)
                col1.metric("💰 Patrimônio em " + str(max_years) + " anos", f"R$ {final_wealth:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                col2.metric("📈 Renda Mensal em " + str(max_years) + " anos", f"R$ {final_income:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

def main():
    st.sidebar.title("📊 Dashboard FIIs IFIX")
    st.sidebar.markdown("---")
    page = st.sidebar.radio("🧭 Navegação", ["🔍 Explorar FIIs", "💼 Minha Carteira", "🎯 Projeções"])

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔔 Alertas de DY")
    dy_min = st.sidebar.number_input(
        "DY mínimo (%)", min_value=0.0, max_value=50.0, value=6.0, step=0.5, format="%.1f",
        help="FIIs abaixo deste DY serão destacados em vermelho na carteira"
    )
    dy_max = st.sidebar.number_input(
        "DY máximo (%)", min_value=0.0, max_value=100.0, value=15.0, step=0.5, format="%.1f",
        help="FIIs acima deste DY serão destacados em laranja (possível sinal de risco)"
    )

    st.sidebar.markdown("---")
    st.sidebar.success("✅ **Conectado à Brapi**")
    st.sidebar.info("💡 **Preços:** Brapi")
    st.sidebar.info("📊 **DY:** Funds Explorer + Status Invest")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📚 Sobre")
    st.sidebar.markdown("Dashboard para controle de investimentos em FIIs brasileiros.")
    st.sidebar.markdown("**Fontes de dados:**")
    st.sidebar.markdown("- Preços: [Brapi](https://brapi.dev)")
    st.sidebar.markdown("- DY: [Funds Explorer](https://fundsexplorer.com.br) + [Status Invest](https://statusinvest.com.br)")

    if page == "🔍 Explorar FIIs":
        page_explore()
    elif page == "💼 Minha Carteira":
        page_portfolio(dy_min=dy_min, dy_max=dy_max)
    else:
        page_projection()

if __name__ == "__main__":
    main()