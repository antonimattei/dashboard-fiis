# 📊 Dashboard Invest BR

Dashboard interativo em Streamlit para gerenciar e analisar investimentos brasileiros: **FIIs, Ações e ETFs**. Acompanhe sua carteira, explore ativos, registre proventos e projete sua jornada rumo à independência financeira.

---

## ✨ Funcionalidades

- **Explorar Ativos** — lista completa de FIIs, Ações e ETFs com preços em tempo real e Dividend Yield (DY) de 12 meses; busca por ticker ou nome; filtro por tipo
- **Minha Carteira** — adicione e gerencie posições com cálculo automático de preço médio; alertas de DY configuráveis; alocação por ativo e por tipo; comparativo vs IFIX ou Ibovespa; exportação CSV
- **Resumo Fiscal** — ganho de capital latente e IR estimado por tipo de ativo (FII 20%, Ações 15%, ETFs 15%)
- **Histórico de Proventos** — registro de dividendos/rendimentos recebidos com gráfico mensal e exportação CSV
- **Projeções de IF** — simulação de crescimento de patrimônio e renda passiva com horizonte configurável de até 50 anos

---

## 🗂 Estrutura do Projeto

```
dashboard-fiis/
├── app.py                  # Entry point — configuração e roteamento de páginas
├── config.py               # Constantes globais (paths, IR, listas de ativos)
├── utils.py                # Formatação (brl, pct), simulação de projeção
├── api/
│   ├── prices.py           # Preços via Brapi REST; benchmark via yfinance
│   └── scraping.py         # DY via FundsExplorer e StatusInvest
├── data_layer/
│   ├── assets.py           # Lista de ativos com cache CSV 30 min
│   ├── portfolio.py        # I/O e métricas do portfólio
│   └── proventos.py        # I/O do histórico de proventos
├── pages/
│   ├── explore.py          # Página: Explorar Ativos
│   ├── portfolio.py        # Página: Minha Carteira
│   └── projection.py       # Página: Projeções de IF
├── tests/
│   └── test_app.py         # 28 testes unitários (pytest)
├── data/                   # Gerado em execução — NÃO commitar
│   ├── ativos.csv          # Cache de ativos e preços (30 min)
│   ├── portfolio.json      # Carteira do usuário
│   ├── proventos.json      # Histórico de proventos
│   └── dashboard.log       # Log de execução
├── requirements.txt
├── .env                    # Variáveis de ambiente (NÃO commitar)
├── .env.example
└── pytest.ini
```

---

## 🚀 Instalação e Execução

### 1. Clone o repositório

```bash
git clone https://github.com/antonimattei/dashboard-fiis.git
cd dashboard-fiis
```

### 2. Crie e ative um ambiente virtual

```bash
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure a chave da Brapi

Crie o arquivo `.env` a partir do exemplo:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Edite `.env` e insira sua chave (obtenha gratuitamente em [brapi.dev](https://brapi.dev)):

```
BRAPI_API_KEY=SUA_CHAVE_AQUI
```

> **Importante:** o arquivo `.env` está no `.gitignore` e nunca deve ser commitado.

### 5. Execute o dashboard

```bash
streamlit run app.py
```

O dashboard abrirá automaticamente em [http://localhost:8501](http://localhost:8501).

---

## 🧪 Testes

```bash
pytest tests/
```

28 testes unitários cobrindo: classificação de tickers, operações de carteira (compra/venda/PM), projeções financeiras, e persistência de portfólio e proventos.

---

## 📡 Fontes de Dados

| Dado | Fonte |
|---|---|
| Preços de ativos | [Brapi](https://brapi.dev) — REST API |
| Lista de FIIs e ETFs | [Brapi](https://brapi.dev) — `quote/list?type=fund` |
| Lista de Ações | [Brapi](https://brapi.dev) — `quote/list?type=stock` |
| Dividend Yield (FIIs) | [FundsExplorer](https://fundsexplorer.com.br) + [StatusInvest](https://statusinvest.com.br) |
| Dividend Yield (Ações/ETFs) | [StatusInvest](https://statusinvest.com.br) |
| Benchmark IFIX / Ibovespa | [yfinance](https://github.com/ranaroussi/yfinance) |

> Preços são cacheados localmente por 30 minutos. DY é cacheado por 24 horas.

---

## 🛡️ Segurança

- Nunca commite o arquivo `.env` — a chave da API é dado sensível
- A pasta `data/` contém dados pessoais de carteira — adicione ao `.gitignore` se usar repositório público

---

## 📝 Licença

Distribuído sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
