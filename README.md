# OpenDataSUS — Dados Abertos do SUS

[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-CC--BY--4.0-green)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](https://python.org)
[![DataSUS](https://img.shields.io/badge/data-OpenDataSUS-orange)](https://dadosabertos.saude.gov.br)

> Acesse **101 datasets oficiais do Ministério da Saúde** diretamente do bucket público S3 da AWS. Sem autenticação, sem dependências externas — apenas Python 3 padrão.

Este repositório contém uma **skill para agentes de IA** (Claude Code, Cursor, OpenCode, Windsurf, GitHub Copilot, etc.) que permite consultar dados reais de saúde pública do Brasil sem fabricar ou alucinar informações.

## Funcionalidades

- Listar e buscar nos 101 datasets oficiais do OpenDataSUS
- Inspecionar metadados e recursos de qualquer dataset
- Consultar dados CSV (incluindo arquivos ZIP) com filtros e agregações
- Streaming de arquivos grandes (centenas de MB) sem carregar em memória
- Suporte a ZIP, CSV, JSON
- Zero dependências — apenas Python 3 stdlib

## Quick start

```bash
git clone https://github.com/seu-usuario/opendatasus-skill.git
cd opendatasus-skill

# Sem instalação — execute diretamente
python3 opendatasus.py list
python3 opendatasus.py info srag-2019-a-2026
python3 opendatasus.py query srag-2019-a-2026 --sample
```

## Uso

### Listar datasets

```bash
# Todos os datasets
python3 opendatasus.py list

# Filtrar por categoria
python3 opendatasus.py list --grupo "Vigilancia"

# Buscar por palavra-chave
python3 opendatasus.py list --search "dengue"

# Filtrar por formato
python3 opendatasus.py list --formato CSV

# Saída JSON
python3 opendatasus.py list --json
```

### Inspecionar dataset

```bash
python3 opendatasus.py info srag-2019-a-2026
python3 opendatasus.py info sim
python3 opendatasus.py info covid-19-vacinacao
```

### Consultar dados

```bash
# Amostra de dados
python3 opendatasus.py query srag-2019-a-2026 --sample

# Filtrar por coluna
python3 opendatasus.py query srag-2019-a-2026 --filter "CLASSI_FIN=3" --group SG_UF

# Múltiplos filtros
python3 opendatasus.py query srag-2019-a-2026 --filter "CLASSI_FIN=3" --filter "EVOLUCAO=2" --group SG_UF

# Agregações
python3 opendatasus.py query arboviroses-dengue --group "NU_ANO" --filter "SG_UF=SP"

# Selecionar recurso específico
python3 opendatasus.py info sim
python3 opendatasus.py query sim --recurso 48 --sample   # Mortalidade 2025

# Colunas específicas
python3 opendatasus.py query srag-2019-a-2026 --colunas "CLASSI_FIN,SG_UF,EVOLUCAO" --sample
```

## Como usar como skill de IA

### Claude Code

Coloque `SKILL.md` na raiz do projeto ou em `CLAUDE.md`. Claude Code lê automaticamente.

### Cursor

Coloque `SKILL.md` em `.cursor/rules/` ou use `@Skills` para referenciar.

### OpenCode

Adicione no `opencode.json`:
```json
{
  "skills": ["caminho/para/SKILL.md"]
}
```

### Aider

Use `--read SKILL.md` para carregar as instruções.

### Manual

```
cat SKILL.md | pbcopy  # copie e cole no prompt do agente
```

## Datasets disponíveis

| Dataset | Descrição | Tamanho aproximado |
|---------|-----------|-------------------|
| `srag-2019-a-2026` | SRAG (COVID, Influenza, VSR) | ~500 MB/ano |
| `sim` | Sistema de Informação sobre Mortalidade (1979-hoje) | ~200 MB/ano |
| `sistema-de-informacao-sobre-nascidos-vivos-sinasc` | Nascidos Vivos | ~50 MB/ano |
| `covid-19-vacinacao` | Vacinação COVID-19 | ~1 GB (total) |
| `arboviroses-dengue` | Dengue (2000-hoje) | ~100 MB/ano |
| `cnes-cadastro-nacional-de-estabelecimentos-de-saude` | Estabelecimentos de saúde | ~50 MB |
| `hospitais-e-leitos` | Leitos hospitalares | ~20 MB |
| `bps` | Banco de Preços em Saúde | ~100 MB |

Para listar todos: `python3 opendatasus.py list`

## Arquitetura

```
                    ┌──────────────────┐
                    │  OpenAI / Claude │
                    │  (AI Agent)      │
                    └────────┬─────────┘
                             │ reads SKILL.md
                             ▼
                    ┌──────────────────┐
                    │  opendatasus.py  │  ← Python 3 stdlib
                    └────────┬─────────┘
                             │ HTTPS (no auth)
                             ▼
                    ┌──────────────────┐
                    │  OpenDataSUS     │  ← dadosabertos.saude.gov.br
                    │  (Next.js)       │
                    └────────┬─────────┘
                             │ S3 redirect
                             ▼
                    ┌──────────────────┐
                    │  AWS S3 (público)│  ← ckan.saude.gov.br
                    │  CSV / JSON / ZIP│
                    └──────────────────┘
```

## Licença

Este projeto é distribuído sob a licença **Creative Commons Attribution 4.0 International (CC-BY-4.0)** — mesma licença dos dados do OpenDataSUS.

## Links

- [Portal OpenDataSUS](https://dadosabertos.saude.gov.br)
- [API de Dados Abertos](https://apidadosabertos.saude.gov.br)
- [Portal Brasileiro de Dados Abertos](https://dados.gov.br)
- [Ministério da Saúde](https://www.gov.br/saude)
