"""Constantes e configurações globais do Dashboard Invest BR."""
import os

DATA_DIR = "data"
ATIVOS_CSV = os.path.join(DATA_DIR, "ativos.csv")
PORTFOLIO_JSON = os.path.join(DATA_DIR, "portfolio.json")
PROVENTOS_JSON = os.path.join(DATA_DIR, "proventos.json")

# Alíquotas de IR por tipo de ativo
ASSET_CONFIG = {
    "FII":  {"ir_ganho": 0.20, "ir_dividendo": 0.00},
    "Ação": {"ir_ganho": 0.15, "ir_dividendo": 0.00},
    "ETF":  {"ir_ganho": 0.15, "ir_dividendo": 0.00},
}

# ETFs de índice conhecidos (terminam em 11 mas não são FIIs)
ETFS_BR = {
    "BOVA11","SMAL11","IVVB11","GOLD11","HASH11","XFIX11","SPXI11",
    "DIVO11","FIND11","MATB11","ACWI11","NASD11","FIXA11","GOVE11",
    "BBSD11","IMAB11","IRFM11","LFTE11","MOVA11","TRIG11",
}

# FIIs conhecidos — fallback offline
FIIS_FALLBACK = [
    "ALZR11","BCFF11","BRCR11","BTLG11","CVBI11","DEVA11","GALG11",
    "GGRC11","HGBS11","HGCR11","HGFF11","HGLG11","HGPO11","HGRE11",
    "HGRU11","HSML11","HTMX11","IRDM11","JSRE11","KNHY11","KNIP11",
    "KNCR11","KNRI11","KNSC11","LVBI11","MALL11","MXRF11","PATL11",
    "PVBI11","RBRF11","RBRP11","RBRY11","RBRR11","RECT11","RECR11",
    "RNGO11","RURA11","RZTR11","SADI11","TGAR11","TRXF11","VGIR11",
    "VIFI11","VILG11","VINO11","VISC11","VRTA11","XPCI11","XPLG11","XPML11",
]

# Ações do Ibovespa — fallback offline
ACOES_FALLBACK = [
    "ITUB4","PETR4","VALE3","BBDC4","ABEV3","B3SA3","WEGE3","RENT3",
    "BBAS3","SUZB3","EGIE3","RDOR3","SBSP3","ENEV3","VIVT3","GGBR4",
    "PRIO3","CPLE6","JBSS3","MRVE3","CYRE3","MULT3","LREN3","MGLU3",
    "PETZ3","RECV3","RADL3","TOTS3","EMBR3","BEEF3",
]
