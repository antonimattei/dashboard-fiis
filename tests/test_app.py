"""
Testes unitários — Dashboard Investimentos BR.
Execute com: pytest tests/
"""
import json
import os
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_layer.portfolio import upsert_position, clean_positions, save_portfolio, load_portfolio
from data_layer.assets import classify_ticker
from data_layer.proventos import add_provento, load_proventos
from utils import simulate_projection
import data_layer.portfolio as _portfolio_mod
import data_layer.proventos as _proventos_mod


# ============= Helpers =============

def _make_portfolio(*positions):
    return {"positions": list(positions)}

def _pos(ticker, quantity, avg_price):
    return {"ticker": ticker, "quantity": quantity, "avg_price": avg_price}


# ============= classify_ticker =============

class TestClassifyTicker:
    def test_fii(self):
        assert classify_ticker("HGLG11") == "FII"
        assert classify_ticker("MXRF11") == "FII"
        assert classify_ticker("XPML11") == "FII"

    def test_etf(self):
        assert classify_ticker("BOVA11") == "ETF"
        assert classify_ticker("SMAL11") == "ETF"
        assert classify_ticker("IVVB11") == "ETF"

    def test_acao(self):
        assert classify_ticker("ITUB4") == "Ação"
        assert classify_ticker("PETR4") == "Ação"
        assert classify_ticker("VALE3") == "Ação"

    def test_case_insensitive(self):
        assert classify_ticker("hglg11") == "FII"
        assert classify_ticker("bova11") == "ETF"
        assert classify_ticker("itub4") == "Ação"


# ============= upsert_position =============

class TestUpsertPosition:
    def test_adiciona_nova_posicao(self):
        pf = _make_portfolio()
        upsert_position(pf, "HGLG11", 100, 150.0)
        assert len(pf["positions"]) == 1
        pos = pf["positions"][0]
        assert pos["ticker"] == "HGLG11"
        assert pos["quantity"] == 100
        assert pos["avg_price"] == 150.0

    def test_normaliza_ticker_para_maiusculo(self):
        pf = _make_portfolio()
        upsert_position(pf, "hglg11", 10, 100.0)
        assert pf["positions"][0]["ticker"] == "HGLG11"

    def test_compra_adicional_calcula_preco_medio(self):
        pf = _make_portfolio(_pos("KNRI11", 100, 200.0))
        upsert_position(pf, "KNRI11", 100, 220.0)
        pos = pf["positions"][0]
        assert pos["quantity"] == 200
        assert pos["avg_price"] == pytest.approx(210.0)

    def test_venda_parcial_reduz_quantidade_sem_alterar_pm(self):
        pf = _make_portfolio(_pos("XPML11", 200, 100.0))
        upsert_position(pf, "XPML11", -50, 110.0)
        pos = pf["positions"][0]
        assert pos["quantity"] == 150
        assert pos["avg_price"] == pytest.approx(100.0)

    def test_venda_total_zera_quantidade(self):
        pf = _make_portfolio(_pos("MXRF11", 50, 10.0))
        upsert_position(pf, "MXRF11", -50, 11.0)
        assert pf["positions"][0]["quantity"] == 0

    def test_venda_acima_do_estoque_nao_vai_negativo(self):
        pf = _make_portfolio(_pos("BTLG11", 30, 80.0))
        upsert_position(pf, "BTLG11", -100, 90.0)
        assert pf["positions"][0]["quantity"] == 0

    def test_multiplos_tickers_independentes(self):
        pf = _make_portfolio(_pos("HGLG11", 10, 100.0), _pos("KNRI11", 20, 200.0))
        upsert_position(pf, "HGLG11", 10, 120.0)
        hglg = next(p for p in pf["positions"] if p["ticker"] == "HGLG11")
        knri = next(p for p in pf["positions"] if p["ticker"] == "KNRI11")
        assert hglg["quantity"] == 20
        assert hglg["avg_price"] == pytest.approx(110.0)
        assert knri["quantity"] == 20

    def test_acao_funciona_igual_a_fii(self):
        pf = _make_portfolio()
        upsert_position(pf, "ITUB4", 100, 30.0)
        upsert_position(pf, "ITUB4", 100, 40.0)
        pos = pf["positions"][0]
        assert pos["quantity"] == 200
        assert pos["avg_price"] == pytest.approx(35.0)


# ============= clean_positions =============

class TestCleanPositions:
    def test_remove_posicoes_zeradas(self):
        pf = _make_portfolio(
            _pos("HGLG11", 10, 100.0),
            _pos("KNRI11", 0, 200.0),
            _pos("XPML11", 5, 50.0),
        )
        clean_positions(pf)
        tickers = [p["ticker"] for p in pf["positions"]]
        assert "KNRI11" not in tickers
        assert "HGLG11" in tickers
        assert "XPML11" in tickers

    def test_portfolio_vazio_permanece_vazio(self):
        pf = _make_portfolio()
        clean_positions(pf)
        assert pf["positions"] == []

    def test_todas_zeradas_resulta_em_lista_vazia(self):
        pf = _make_portfolio(_pos("A11", 0, 10.0), _pos("B11", 0, 20.0))
        clean_positions(pf)
        assert pf["positions"] == []


# ============= simulate_projection =============

class TestSimulateProjection:
    def test_retorna_dataframe_com_colunas_corretas(self):
        df, _ = simulate_projection(100_000, 700, 1_000, 5_000, max_years=10)
        assert "Data" in df.columns
        assert "Patrimônio (R$)" in df.columns
        assert "Renda Mensal (R$)" in df.columns

    def test_numero_de_pontos_correto(self):
        df, _ = simulate_projection(50_000, 300, 500, 5_000, max_years=5)
        assert len(df) == 5 * 12

    def test_patrimonio_cresce_com_aportes(self):
        df, _ = simulate_projection(10_000, 70, 500, 99_999, max_years=10)
        assert df["Patrimônio (R$)"].iloc[-1] > df["Patrimônio (R$)"].iloc[0]

    def test_meta_atingida_retorna_mes_valido(self):
        _, months = simulate_projection(10_000_000, 70_000, 0, 5_000, max_years=5)
        assert months == 0

    def test_meta_nao_atingida_retorna_none(self):
        _, months = simulate_projection(100, 1, 0, 99_999, yearly_return=0.001, max_years=1)
        assert months is None

    def test_sem_capital_inicial_usa_yield_padrao(self):
        df, _ = simulate_projection(0, 0, 1_000, 5_000, max_years=5)
        assert len(df) == 60

    def test_patrimonio_nunca_negativo_com_aportes_positivos(self):
        df, _ = simulate_projection(1_000, 7, 500, 5_000, max_years=10)
        assert (df["Patrimônio (R$)"] >= 0).all()


# ============= Portfolio I/O =============

class TestPortfolioIO:
    def test_salva_e_carrega_portfolio(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_portfolio_mod, "PORTFOLIO_JSON", str(tmp_path / "portfolio.json"))
        monkeypatch.setattr(_portfolio_mod, "DATA_DIR", str(tmp_path))
        pf = {"positions": [_pos("HGLG11", 10, 100.0)]}
        save_portfolio(pf)
        loaded = load_portfolio()
        assert loaded["positions"][0]["ticker"] == "HGLG11"
        assert loaded["positions"][0]["quantity"] == 10

    def test_carrega_portfolio_inexistente_retorna_vazio(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_portfolio_mod, "PORTFOLIO_JSON", str(tmp_path / "nao_existe.json"))
        loaded = load_portfolio()
        assert loaded == {"positions": []}

    def test_carrega_portfolio_corrompido_retorna_vazio(self, tmp_path, monkeypatch):
        json_path = tmp_path / "portfolio.json"
        json_path.write_text("INVALID JSON {{{", encoding="utf-8")
        monkeypatch.setattr(_portfolio_mod, "PORTFOLIO_JSON", str(json_path))
        monkeypatch.setattr(_portfolio_mod, "DATA_DIR", str(tmp_path))
        loaded = load_portfolio()
        assert loaded == {"positions": []}


# ============= Proventos I/O =============

class TestProventosIO:
    def test_salva_e_carrega_provento(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_proventos_mod, "PROVENTOS_JSON", str(tmp_path / "proventos.json"))
        monkeypatch.setattr(_proventos_mod, "DATA_DIR", str(tmp_path))
        add_provento("HGLG11", "2026-03-01", 0.85, 100)
        proventos = load_proventos()
        assert len(proventos) == 1
        assert proventos[0]["ticker"] == "HGLG11"
        assert proventos[0]["total"] == pytest.approx(85.0)

    def test_proventos_ordenados_por_data_desc(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_proventos_mod, "PROVENTOS_JSON", str(tmp_path / "proventos.json"))
        monkeypatch.setattr(_proventos_mod, "DATA_DIR", str(tmp_path))
        add_provento("HGLG11", "2026-01-01", 0.80, 10)
        add_provento("KNRI11", "2026-03-01", 0.90, 10)
        proventos = load_proventos()
        assert proventos[0]["data"] > proventos[1]["data"]

    def test_carrega_proventos_inexistente_retorna_vazio(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_proventos_mod, "PROVENTOS_JSON", str(tmp_path / "nao_existe.json"))
        assert load_proventos() == []
