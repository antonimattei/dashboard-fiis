import json
import os
from datetime import datetime
import requests
from bs4 import BeautifulSoup

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dateutil.relativedelta import relativedelta
from brapi import Brapi
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configuração da Brapi
BRAPI_API_KEY = os.getenv("BRAPI_API_KEY")

if not BRAPI_API_KEY:
    st.error("❌ BRAPI_API_KEY não encontrada! Configure o arquivo .env")
    st.stop()

client = Brapi(api_key=BRAPI_API_KEY)

DATA_DIR = "data"
IFIX_CSV = os.path.join(DATA_DIR, "ifix_tickers.csv")
PORTFOLIO_JSON = os.path.join(DATA_DIR, "portfolio.json")

st.set_page_config(page_title="Dashboard FIIs IFIX", layout="wide")

# ... resto do código permanece igual

print("🔍 Buscando lista de ações disponíveis na Brapi...")

try:
    # Buscar lista completa de ações
    stocks_response = client.quote.list()
    
    # Filtrar apenas FIIs (terminam com 11)
    fiis = []
    
    for stock in stocks_response.stocks:
        ticker = stock.stock
        # FIIs geralmente terminam com 11
        if ticker.endswith('11'):
            fiis.append({
                'ticker': ticker,
                'nome': stock.name if hasattr(stock, 'name') else ticker,
                'tipo': stock.type if hasattr(stock, 'type') else 'FII'
            })
    
    print(f"✅ Encontrados {len(fiis)} FIIs")
    
    # Criar DataFrame
    df = pd.DataFrame(fiis)
    
    # Ordenar por ticker
    df = df.sort_values('ticker').reset_index(drop=True)
    
    # Criar diretório se não existir
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Salvar CSV
    df.to_csv(IFIX_CSV, index=False, encoding='utf-8')
    
    print(f"✅ Arquivo '{IFIX_CSV}' atualizado com sucesso!")
    print(f"📊 Total de FIIs: {len(df)}")
    print("\n📋 Primeiros 10 FIIs:")
    print(df.head(10).to_string(index=False))
    
except Exception as e:
    print(f"❌ Erro ao buscar dados: {str(e)}")
    print("\n💡 Tentando método alternativo...")
    
    # Método alternativo: buscar FIIs conhecidos do IFIX
    fiis_conhecidos = [
        'HGLG11', 'KNRI11', 'XPML11', 'BTLG11', 'VISC11',
        'MXRF11', 'BCFF11', 'KNCR11', 'GGRC11', 'HGRU11',
        'PVBI11', 'RBRR11', 'RZTR11', 'VILG11', 'XPLG11',
        'ALZR11', 'BRCR11', 'CVBI11', 'DEVA11', 'GALG11',
        'HGBS11', 'HGCR11', 'HGFF11', 'HGPO11', 'HGRE11',
        'HSML11', 'HTMX11', 'IRDM11', 'JSRE11', 'KNHY11',
        'KNIP11', 'KNSC11', 'LVBI11', 'MALL11', 'PATL11',
        'RBRF11', 'RBRP11', 'RBRY11', 'RECT11', 'RECR11',
        'RNGO11', 'RURA11', 'SADI11', 'TGAR11', 'TRXF11',
        'VGIR11', 'VIFI11', 'VINO11', 'VRTA11', 'XPCI11'
    ]
    
    fiis_data = []
    print(f"\n🔄 Buscando informações de {len(fiis_conhecidos)} FIIs...")
    
    for i, ticker in enumerate(fiis_conhecidos, 1):
        try:
            quote = client.quote.retrieve(tickers=ticker)
            if quote.results and len(quote.results) > 0:
                result = quote.results[0]
                nome = result.short_name if hasattr(result, 'short_name') else ticker
                fiis_data.append({
                    'ticker': ticker,
                    'nome': nome,
                    'tipo': 'FII'
                })
                print(f"  ✓ {i}/{len(fiis_conhecidos)}: {ticker} - {nome}")
        except:
            fiis_data.append({
                'ticker': ticker,
                'nome': ticker,
                'tipo': 'FII'
            })
            print(f"  ⚠ {i}/{len(fiis_conhecidos)}: {ticker} - Sem dados")
    
    df = pd.DataFrame(fiis_data)
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(IFIX_CSV, index=False, encoding='utf-8')
    
    print(f"\n✅ Arquivo '{IFIX_CSV}' criado com {len(df)} FIIs!")