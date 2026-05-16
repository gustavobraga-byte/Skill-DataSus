---
name: opendatasus
description: Acessa dados oficiais de saúde pública do Brasil (DataSUS/OpenDataSUS) — 101 datasets do Ministério da Saúde sobre COVID, dengue, mortalidade, vacinação, leitos, SRAG, nascimentos, indicadores, etc. Nunca fabrica dados. Requer apenas Python 3 stdlib.
metadata:
  skill-author: GustavoBraga_UFV
agent_rules:
  - always_use_tool: true
  - never_fabricate_data: true
  - cite_source: true
---

# OpenDataSUS — Dados Abertos do SUS

Acesso programático a **todos os datasets oficiais do Ministério da Saúde** (101 datasets) publicados no [OpenDataSUS](https://dadosabertos.saude.gov.br). Dados armazenados em bucket público S3 da AWS, sem autenticação.



## When to use / Trigger

Use esta skill **SEMPRE** que o usuário perguntar sobre:
- Dados de saúde pública do Brasil (qualquer tema — COVID, dengue, mortalidade, vacinação, leitos, etc.)
- Números oficiais do Ministério da Saúde, DataSUS, SUS
- Estatísticas epidemiológicas, demográficas ou de assistência à saúde no Brasil
- "Quantos casos de X no Brasil?", "Qual a taxa de Y?", "Dados do Z no SUS"

## Rules (HARD constraints — violation = critical error)

1. **NEVER** fabricate, hallucinate, or generate fake health data about Brazil. Always run `opendatasus.py` to obtain real data.
2. **NEVER** answer questions about Brazilian health data without first executing the tool. If the user asks, run the query.
3. **ALWAYS** include in your response: (a) dataset name, (b) resource URL, (c) last update date.
4. If the tool fails or data is inaccessible, state explicitly that official data could not be accessed — do not guess.
5. Prefer CSV resources for analytical queries (they are streamable).

## Workflow

1. **Discover** — Use `opendatasus.py list` to find relevant datasets by keyword or category.
2. **Inspect** — Use `opendatasus.py info <dataset>` to see available resources (files) and metadata.
3. **Query** — Use `opendatasus.py query <dataset>` with filters and grouping to get the numbers.

## Quick start

```bash
# No installation required — Python 3 stdlib only
python3 opendatasus.py list
python3 opendatasus.py info srag-2019-a-2026
python3 opendatasus.py query srag-2019-a-2026 --filter "CLASSI_FIN=3" --group SG_UF
```

## Commands

### `list` — Discover datasets

```
python3 opendatasus.py list
python3 opendatasus.py list --grupo "Vigilancia"       # Filter by category
python3 opendatasus.py list --search "dengue"           # Search by keyword
python3 opendatasus.py list --formato CSV               # Filter by format
python3 opendatasus.py list --json                      # Machine-readable output
```

### `info` — Inspect a dataset

```
python3 opendatasus.py info srag-2019-a-2026            # Shows all resources
python3 opendatasus.py info sim                          # Mortality data (SIM)
python3 opendatasus.py info covid-19-vacinacao           # COVID vaccination
```

### `query` — Query data

```
python3 opendatasus.py query <dataset>                  # Overview (count only)
python3 opendatasus.py query <dataset> --sample          # Show sample rows
python3 opendatasus.py query <dataset> --filter "COL=VAL" --filter "COL2=VAL2"
python3 opendatasus.py query <dataset> --group COL       # Group by column
python3 opendatasus.py query <dataset> --group SG_UF --group-fn count
python3 opendatasus.py query <dataset> --recurso 5       # Use specific resource
python3 opendatasus.py query <dataset> --colunas COL1,COL2 --sample
python3 opendatasus.py query <dataset> --limit 1000      # Limit processing
python3 opendatasus.py query <dataset> --json            # JSON output
```

## Dataset catalog (101 datasets)

| Category | Datasets |
|----------|----------|
| Arboviroses | Sinan/Dengue, Sinan/Febre de Chikungunya, Sinan/Zika, Febre Amarela |
| Assistência à saúde | CNES, UBS, Hospitais e Leitos, Ocupação Hospitalar COVID-19 |
| Vacinação | PNI (2020-2026), COVID-19 Vacinação, ESAVI, SIES |
| Vigilância | SRAG (2009-2026), SIM (Mortalidade), Sinasc (Nascidos Vivos), Mpox, Síndrome Gripal (2020-2024) |
| Atenção Primária | SISVAN, ENANI, Sisab, Mais Médicos |
| Indicadores | RIPSA (Socioeconômico, Recursos, Mortalidade, Morbidade, Demográfico, Cobertura, Fatores de Risco), MGDI (todos) |
| Saúde Indígena | SIASI (vários módulos), SESAI RH, SasiSUS |
| Assistência Farmacêutica | BNAFAR Estoque, BPS (Banco de Preços) |
| Saneamento | SISAGUA (Captação, Tratamento, Controle, Vigilância) |
| Economia | SIOPS, APURASUS |
| Ciência & Tecnologia | Conitec, PCDT |

## Key datasets

| Dataset name | Content | Update |
|---|---|---|
| `srag-2019-a-2026` | SRAG (COVID-19, Influenza, VSR, other respiratory viruses) | Weekly |
| `srag-2009-2012`, `srag-2013-2018` | Historical SRAG data | Static |
| `sim` | Mortality records (1979-present) | Annual |
| `sistema-de-informacao-sobre-nascidos-vivos-sinasc` | Birth records | Annual |
| `covid-19-vacinacao` | COVID-19 vaccination campaign | Daily |
| `arboviroses-dengue` | Dengue cases (Sinan) | Weekly |
| `cnes-cadastro-nacional-de-estabelecimentos-de-saude` | Health facilities registry | Monthly |
| `hospitais-e-leitos` | Hospital beds | Monthly |
| `bps` | Health procurement prices | Monthly |
| `registro-de-ocupacao-hospitalar-covid-19` | COVID-19 bed occupancy | Daily (historical) |

## Dependencies

- Python 3 (stdlib only: csv, json, urllib, zipfile, argparse)
- No pip packages, no venv, no virtual environment needed

## Data source

- **Portal:** https://dadosabertos.saude.gov.br
- **License:** Creative Commons Attribution (CC-BY)
- **Storage:** AWS S3 `s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/...`
- **API:** https://apidadosabertos.saude.gov.br (Swagger/OpenAPI)
