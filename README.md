# Case Verx
Resolução de case técnico para o processo seletivo da Verx.

## Estrutura Inicial

.
├── app/
│   ├── __init__.py
│   ├── cli.py                  # Entrada do programa
│   ├── crawler_service.py      # Orquestra o fluxo
│   ├── selenium_client.py      # Selenium (navegação)
│   ├── parser.py               # BeautifulSoup
│   └── csv_writer.py           # Escrita CSV

## Fluxo Inicial da aplicação 

1 - CLI recebe region

2 - Selenium acessa Yahoo Finance Equity Screener

3 - Aplica filtro por região

4 - Percorre todas as páginas

5 - Coleta HTML

6 - BeautifulSoup extrai: 

- symbol

- name

- price

7 - Salva CSV

8 - Exibe resumo no log