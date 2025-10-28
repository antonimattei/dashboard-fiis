# 📊 Dashboard FIIs IFIX

Um dashboard interativo em Streamlit para gerenciar e analisar investimentos em Fundos de Investimento Imobiliário (FIIs) brasileiros listados no índice IFIX. Este projeto visa fornecer uma ferramenta completa para acompanhar sua carteira, explorar novos FIIs e projetar sua jornada rumo à independência financeira.

## ✨ Funcionalidades

-   **Exploração de FIIs**: Visualize uma lista completa de FIIs do IFIX, com preços atualizados e Dividend Yield (DY) de 12 meses.
-   **Gestão de Carteira**: Adicione, remova e atualize suas posições em FIIs, registrando quantidade e preço médio de compra.
-   **Métricas da Carteira**: Acompanhe o valor de mercado total, a renda mensal estimada e o DY médio da sua carteira.
-   **Projeções de Independência Financeira**: Simule cenários de crescimento de patrimônio e renda passiva com base em aportes, valorização e crescimento de dividendos, com explicações detalhadas.
-   **Persistência de Dados**: Os dados da sua carteira e as métricas dos FIIs explorados são salvos localmente, garantindo que suas informações não se percam entre as sessões.

## 🚀 Tecnologias Utilizadas

-   **Python**: Linguagem de programação principal.
-   **Streamlit**: Framework para construção rápida da interface web interativa.
-   **Pandas**: Manipulação e análise de dados.
-   **Plotly**: Geração de gráficos interativos para visualizações.
-   **Brapi**: API para obtenção de preços de FIIs.
-   **BeautifulSoup4 & Requests**: Web scraping para obtenção de Dividend Yield de fontes gratuitas (Funds Explorer e Status Invest).
-   **python-dotenv**: Gerenciamento seguro de variáveis de ambiente (API Keys).

## ⚙️ Configuração e Instalação

Siga os passos abaixo para configurar e rodar o dashboard em sua máquina local.


### 1. Clone o Repositório

Primeiro, clone este repositório para o seu ambiente local:


git clone https://github.com/antonimattei/dashboard-fiis.git
cd dashboard-fiis


### 2. Crie e Ative um Ambiente Virtual (Recomendado)
É uma boa prática usar um ambiente virtual para isolar as dependências do projeto:

bash
Copy
python -m venv venv
# No Windows
.\venv\Scripts\activate
# No macOS/Linux
source venv/bin/activate


### 3. Instale as Dependências
Instale todas as bibliotecas Python necessárias listadas no requirements.txt:

bash
Copy
pip install -r requirements.txt


### 4. Configure as Variáveis de Ambiente
Para proteger sua chave da API da Brapi, usaremos variáveis de ambiente.

Crie o arquivo .env:
Copie o arquivo de exemplo .env.example para um novo arquivo chamado .env na raiz do projeto:
bash
Copy
copy .env.example .env # No Windows
cp .env.example .env   # No macOS/Linux
Obtenha sua chave da Brapi:
Acesse o site da Brapi.
Crie uma conta gratuita.
Após o login, localize e copie sua API Key.
Edite o arquivo .env:
Abra o arquivo .env que você acabou de criar e cole sua chave da API:
BRAPI_API_KEY=SUA_CHAVE_DA_API_AQUI
Importante: O arquivo .env está listado no .gitignore e NÃO DEVE SER COMMITADO para o controle de versão. Isso garante que sua chave da API permaneça privada.


### 5. Execute o Dashboard
Com todas as dependências instaladas e a API Key configurada, você pode iniciar o dashboard:

bash
Copy
streamlit run app.py
O Streamlit abrirá automaticamente o dashboard em seu navegador padrão (geralmente em http://localhost:8501).

📁 Estrutura do Projeto
dashboard-fiis/
├── app.py                 # Código principal da aplicação Streamlit
├── requirements.txt       # Lista de dependências do Python
├── .env                   # Variáveis de ambiente (NÃO commitar no Git!)
├── .env.example           # Exemplo de arquivo .env para configuração
├── .gitignore             # Arquivos e pastas ignorados pelo Git
├── data/                  # Pasta para armazenar dados locais
│   ├── ifix_tickers.csv   # Lista de FIIs com preços e DY (atualizado pelo app)
│   └── portfolio.json     # Dados da sua carteira de FIIs
└── README.md              # Este arquivo

🛡️ Segurança e Boas Práticas
Nunca commite o arquivo .env: Sua chave da API é um dado sensível. O .gitignore já está configurado para ignorá-lo.
Mantenha suas dependências atualizadas: Periodicamente, execute pip install -r requirements.txt --upgrade para garantir que você está usando as versões mais recentes das bibliotecas.
Cache de dados: O dashboard utiliza cache para as chamadas de API e web scraping, reduzindo o número de requisições e acelerando o carregamento.
📚 Fontes de Dados
Preços de FIIs: Brapi
Dividend Yield (DY): Funds Explorer e Status Invest (via web scraping)
🤝 Contribuição
Contribuições são bem-vindas! Se você tiver sugestões de melhorias, novas funcionalidades ou encontrar algum bug, sinta-se à vontade para abrir uma issue ou enviar um pull request.

📝 Licença
Este projeto está licenciado sob a licença MIT. Veja o arquivo LICENSE para mais detalhes.
