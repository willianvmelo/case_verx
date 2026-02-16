# Yahoo Finance Equity Screener Crawler

Crawler desenvolvido em Python para extrair dados do **Yahoo Finance Equity Screener**, permitindo filtrar ativos por região e exportar os resultados para CSV.

O sistema automatiza:

- Seleção dinâmica de região
- Navegação por todas as páginas de resultados
- Extração estruturada da tabela
- Exportação para CSV

---

## Funcionalidades

Filtra ativos por país/região  
Percorre automaticamente todas as páginas  
Trata carregamento assíncrono da tabela  
Exporta resultados para CSV  
Implementação orientada a objetos  
Estrutura extensível para novos filtros  

---

## Arquitetura

O projeto segue uma arquitetura modular baseada em camadas:

```
app/
├── cli.py                 # Interface de linha de comando
├── crawler_service.py     # Orquestração do processo
├── selenium_client.py     # Wrapper do WebDriver
├── parser.py              # Parsing HTML → dados estruturados
└── pages/
    └── yahoo_screener_page.py   # Page Object do Yahoo Screener
```

---

## 🛠️ Tecnologias

- Python 3.10+
- Selenium
- BeautifulSoup (bs4)
- lxml
- argparse

---

## Instalação

### Clonar repositório

```bash
git clone <repo-url>
cd <repo>
```

### Criar ambiente virtual

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows:

```powershell
venv\Scripts\activate
```

### Instalar dependências

```bash
pip install -r requirements.txt
```

---

## Dependências do navegador

O crawler utiliza Google Chrome em modo headless.

Certifique-se de que:

- Google Chrome esteja instalado
- Bibliotecas do sistema estejam presentes (Linux/WSL)

Exemplo para Ubuntu/WSL:

```bash
sudo apt update
sudo apt install -y     libnss3     libnspr4     libatk1.0-0     libatk-bridge2.0-0     libxkbcommon0     libgtk-3-0     libgbm1
```

---

## Execução

### Exemplo básico

```bash
python -m app.cli --region Brazil
```

Saída padrão:

```
25 ativos coletados
```

Arquivo gerado:

```
equities.csv
```

### Especificar arquivo de saída

```bash
python -m app.cli --region Austria --output austria_equities.csv
```

---

## Regiões suportadas

Qualquer região disponível no Yahoo Screener:

- Brazil
- United States
- Austria
- Greece
- Germany
- Japan
- etc.

O nome deve corresponder exatamente ao exibido na interface do Yahoo Finance.

---

## Como funciona a extração

### 1. Acesso à página do screener

https://finance.yahoo.com/research-hub/screener/equity/

### 2. Aplicação do filtro de região

- Abre dropdown de filtros
- Desmarca regiões previamente selecionadas
- Marca apenas a região alvo
- Aplica filtro
- Aguarda atualização da tabela

### 3. Paginação automática

O crawler:

- Extrai a página atual
- Clica em **Next**
- Aguarda atualização da tabela
- Repete até o botão Next ficar desabilitado

### 4. Parsing

Os dados são convertidos para estrutura tabular e exportados para CSV.

---

## Estrutura do CSV

Exemplo:

| Symbol | Name | Price |
|------|--------|------|

---

## Considerações técnicas

### Por que Selenium?

O Yahoo Screener utiliza:

- Renderização dinâmica via JavaScript
- Paginação client-side
- Componentes Svelte

Portanto, scraping estático (requests + bs4) não é suficiente.

### Estratégia de confiabilidade

O crawler utiliza múltiplos sinais para detectar atualização da tabela:

- Staleness do DOM
- Mudança na assinatura das primeiras linhas
- Presença de novos elementos

Isso evita inconsistências causadas por delays assíncronos.

---

## Execução com Docker (opcional)

Caso incluído no projeto:

```bash
docker build -t yahoo-crawler .
docker run --rm yahoo-crawler --region Brazil
```

---

## Possível arquitetura em produção (AWS)

Uma arquitetura recomendada para execução em escala:

- ECS Fargate — execução do crawler
- S3 — armazenamento dos resultados
- EventBridge — agendamento periódico
- SQS — fila para múltiplas regiões

---

## Extensões futuras

- Suporte a múltiplos filtros simultâneos
- Exportação para banco de dados
- API REST para disparo de crawls
- Execução paralela por região
- Monitoramento e logs estruturados

---

## Limitações

- Dependência de estrutura atual do site
- Mudanças no DOM podem exigir ajustes
- Execução depende de ambiente com suporte a browser headless

---

## Licença

Projeto desenvolvido exclusivamente para fins de avaliação técnica.

---

## 👤 Autor

Desenvolvido por <Seu Nome>