"""
Testes unitários para funções de cálculo do Dashboard FIIs.
Execute com: pytest tests/
"""
import json
import os
import tempfile
import pytest
import pandas as pd
import sys

# Adiciona raiz do projeto ao path para importar app sem Streamlit
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importações isoladas (sem inicializar Streamlit / Brapi)
from unittest.mock import MagicMock, patch


# ============= Helpers para isolar funções puras =============

def _make_portfolio(*positions):
    """Cria estrutura de portfolio para testes."""
    return {"positions": list(positions)}


def _pos(ticker, quantity, avg_price):
    return {"ticker": ticker, "quantity": quantity, "avg_price": avg_price}


# ============= Importar funções puras diretamente =============
# Fazemos mock das dependências externas antes de importar o módulo

with (
    patch("streamlit.set_page_config"),
    patch("streamlit.error"),
    patch("streamlit.stop"),
    patch("brapi.Brapi"),
    patch("dotenv.load_dotenv"),
    patch.dict(os.environ, {"BRAPI_API_KEY": "fake-key-for-tests"}),
):
    import app as _app


upsert_position = _app.upsert_position
clean_positions = _app.clean_positions
simulate_projection = _app.simulate_projection


# ============= Testes: upsert_position =============

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
        # Compra mais 100 cotas a R$220 → PM = (100*200 + 100*220) / 200 = 210
        upsert_position(pf, "KNRI11", 100, 220.0)
        pos = pf["positions"][0]
        assert pos["quantity"] == 200
        assert pos["avg_price"] == pytest.approx(210.0)

    def test_venda_parcial_reduz_quantidade_sem_alterar_pm(self):
        pf = _make_portfolio(_pos("XPML11", 200, 100.0))
        upsert_position(pf, "XPML11", -50, 110.0)
        pos = pf["positions"][0]
        assert pos["quantity"] == 150
        # PM não deve ser alterado em venda parcial
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
        assert knri["quantity"] == 20  # não alterado


# ============= Testes: clean_positions =============

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


# ============= Testes: simulate_projection =============

class TestSimulateProjection:
    def test_retorna_dataframe_com_colunas_corretas(self):
        df, _ = simulate_projection(
            start_capital=100_000,
            current_monthly_income=700,
            monthly_contribution=1_000,
            target_monthly_income=5_000,
            max_years=10,
        )
        assert "Data" in df.columns
        assert "Patrimônio (R$)" in df.columns
        assert "Renda Mensal (R$)" in df.columns

    def test_numero_de_pontos_correto(self):
        df, _ = simulate_projection(
            start_capital=50_000,
            current_monthly_income=300,
            monthly_contribution=500,
            target_monthly_income=5_000,
            max_years=5,
        )
        assert len(df) == 5 * 12

    def test_patrimonio_cresce_com_aportes(self):
        df, _ = simulate_projection(
            start_capital=10_000,
            current_monthly_income=70,
            monthly_contribution=500,
            target_monthly_income=99_999,
            max_years=10,
        )
        assert df["Patrimônio (R$)"].iloc[-1] > df["Patrimônio (R$)"].iloc[0]

    def test_meta_atingida_retorna_mes_valido(self):
        # Capital alto o suficiente para atingir meta rapidamente
        _, months = simulate_projection(
            start_capital=10_000_000,
            current_monthly_income=70_000,
            monthly_contribution=0,
            target_monthly_income=5_000,
            max_years=5,
        )
        assert months == 0  # já começa acima da meta

    def test_meta_nao_atingida_retorna_none(self):
        _, months = simulate_projection(
            start_capital=100,
            current_monthly_income=1,
            monthly_contribution=0,
            target_monthly_income=99_999,
            yearly_return=0.001,
            max_years=1,
        )
        assert months is None

    def test_sem_capital_inicial_usa_yield_padrao(self):
        # Não deve lançar exceção com capital zero
        df, _ = simulate_projection(
            start_capital=0,
            current_monthly_income=0,
            monthly_contribution=1_000,
            target_monthly_income=5_000,
            max_years=5,
        )
        assert len(df) == 60

    def test_patrimonio_nunca_negativo_com_aportes_positivos(self):
        df, _ = simulate_projection(
            start_capital=1_000,
            current_monthly_income=7,
            monthly_contribution=500,
            target_monthly_income=5_000,
            max_years=10,
        )
        assert (df["Patrimônio (R$)"] >= 0).all()


# ============= Testes: load_portfolio / save_portfolio =============

class TestPortfolioIO:
    def test_salva_e_carrega_portfolio(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_app, "PORTFOLIO_JSON", str(tmp_path / "portfolio.json"))
        monkeypatch.setattr(_app, "DATA_DIR", str(tmp_path))

        pf = {"positions": [_pos("HGLG11", 10, 100.0)]}
        _app.save_portfolio(pf)

        loaded = _app.load_portfolio()
        assert loaded["positions"][0]["ticker"] == "HGLG11"
        assert loaded["positions"][0]["quantity"] == 10

    def test_carrega_portfolio_inexistente_retorna_vazio(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_app, "PORTFOLIO_JSON", str(tmp_path / "nao_existe.json"))
        loaded = _app.load_portfolio()
        assert loaded == {"positions": []}

    def test_carrega_portfolio_corrompido_retorna_vazio(self, tmp_path, monkeypatch):
        json_path = tmp_path / "portfolio.json"
        json_path.write_text("INVALID JSON {{{", encoding="utf-8")
        monkeypatch.setattr(_app, "PORTFOLIO_JSON", str(json_path))
        monkeypatch.setattr(_app, "DATA_DIR", str(tmp_path))

        loaded = _app.load_portfolio()
        assert loaded == {"positions": []}
