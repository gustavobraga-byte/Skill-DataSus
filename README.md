# OpenDataSUS — Dados Abertos do SUS

[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-CC--BY--4.0-green)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](https://python.org)
[![DataSUS](https://img.shields.io/badge/data-OpenDataSUS-orange)](https://dadosabertos.saude.gov.br)

> Acesse **139 datasets oficiais do Ministério da Saúde** diretamente do bucket público S3 da AWS e, como fallback, da API oficial de Dados Abertos do SUS. Sem autenticação, sem dependências externas — apenas Python 3 padrão.

Este repositório contém uma **skill para agentes de IA** (Claude Code, Cursor, OpenCode, Windsurf, GitHub Copilot, etc.) que permite consultar dados reais de saúde pública do Brasil sem fabricar ou alucinar informações.

## Funcionalidades

- Listar, buscar e filtrar os **139 datasets** oficiais do OpenDataSUS
- Inspecionar metadados e recursos de qualquer dataset
- Consultar dados CSV (incluindo arquivos ZIP) com **filtros, agrupamentos e agregações numéricas**
- **Streaming** de arquivos grandes (centenas de MB) sem carregar em memória
- **Delimitador automático** (`;` ou `,`) — SIM usa `;`; SINAN/Dengue e RIPSA usam `,`
- **Colunas case-insensitive** (CSV do SIM usa `SEXO`; API usa `sexo`)
- **Fallback em camadas**: URL do catálogo → variante `/csv/` do bucket → **API oficial** `apidadosabertos.saude.gov.br`
- Suporte a ZIP, CSV e JSON
- Zero dependências — apenas Python 3 stdlib

## Quick start

```bash
git clone https://github.com/gustavobraga-byte/Skill-DataSus.git
cd Skill-DataSus

# Sem instalação — execute diretamente
python3 opendatasus.py list
python3 opendatasus.py info srag-2019-a-2026
python3 opendatasus.py query srag-2019-a-2026 --sample
```

## Uso

### Listar datasets

```bash
# Todos os datasets (139)
python3 opendatasus.py list

# Filtrar por categoria
python3 opendatasus.py list --grupo "Arboviroses"

# Buscar por palavra-chave
python3 opendatasus.py list --search "dengue"

# Filtrar por formato
python3 opendatasus.py list --formato API

# Saída JSON
python3 opendatasus.py list --json
```

### Inspecionar dataset

```bash
python3 opendatasus.py info srag-2019-a-2026
python3 opendatasus.py info sim
python3 opendatasus.py info covid-19-vacinacao
python3 opendatasus.py info arboviroses-dengue
python3 opendatasus.py info cnes-cadastro-nacional-de-estabelecimentos-de-saude
```

### Consultar dados (amostra)

```bash
# Amostra dos primeiros registros
python3 opendatasus.py query srag-2019-a-2026 --sample

# Amostra com projeção de colunas
python3 opendatasus.py query srag-2019-a-2026 --sample --colunas "CLASSI_FIN,SG_UF,EVOLUCAO"
```

### Filtrar e agrupar

```bash
# Filtrar por coluna e agrupar
python3 opendatasus.py query srag-2019-a-2026 --filter "CLASSI_FIN=3" --group "SG_UF"

# Múltiplos filtros
python3 opendatasus.py query srag-2019-a-2026 --filter "CLASSI_FIN=3" --filter "EVOLUCAO=2" --group "SG_UF"

# Agregação numérica (sum/avg/min/max sobre uma coluna)
python3 opendatasus.py query arboviroses-dengue --group "SG_UF" --group-fn avg --group-val "NU_ANO"
```

> **Nota:** a coluna agrupada/filtrada é resolvida de forma **case-insensitive**.
> Ex.: `--group "sexo"` encontra a coluna `SEXO`; `--group "sg_uf"` encontra `SG_UF`.

### Selecionar recurso específico

```bash
# Liste os recursos (índices) de um dataset
python3 opendatasus.py info sim

# Escolha por índice (0 = primeiro, -1 = último)
python3 opendatasus.py query sim --recurso 1 --group "sexo"
python3 opendatasus.py query arboviroses-dengue --recurso -1 --sample
```

## Robustez e Manutenção (v1.2+)

O script opera de forma resiliente frente às mudanças do portal e do bucket:

- **buildId dinâmico**: o hash de cache Next.js do `dadosabertos.saude.gov.br` é descoberto
  automaticamente em runtime (com fallback hardcoded), evitando HTTP 404 quando o portal é recompilado.
- **Delimitador robusto**: a detecção testa o `csv.Sniffer` em múltiplas amostras, valida a
  quebra do cabeçalho e, se necessário, usa heurística de contagem de `;`/`,` na primeira linha —
  superando a instabilidade do Sniffer em arquivos como o SINAN/Dengue (que usa `,`).
- **Caminho `/csv/`**: se a URL do catálogo der 403/404, tenta automaticamente a variante com
  `/csv/` (estrutura atual do bucket S3 do MS).
- **Fallback para a API oficial**: se o bucket estiver inacessível, consulta a API
  `apidadosabertos.saude.gov.br` (rota resolvida via `swagger.json`) com paginação.
- **Colunas case-insensitive**: `--filter` e `--group` ignoram maiúsculas/minúsculas.
- **Índices de recurso negativos**: `--recurso -1` = último recurso.
- **Retry simples**: até 3 tentativas com backoff para tolerar timeouts de rede.
- **Erros amigáveis**: dataset inexistente mostra mensagem clara (não traceback cru).

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

| Dataset | Descrição | Fonte |
|---------|-----------|-------|
| `srag-2019-a-2026` | Síndrome Respiratória Aguda Grave (COVID, Influenza, VSR) | SRAG |
| `sim` | Sistema de Informação sobre Mortalidade (1979–2026) | SIM |
| `sistema-de-informacao-sobre-nascidos-vivos-sinasc` | Nascidos Vivos | SINASC |
| `covid-19-vacinacao` | Campanha de Vacinação contra COVID-19 | PNI |
| `arboviroses-dengue` | Dengue (2000–2026) | Sinan |
| `cnes-cadastro-nacional-de-estabelecimentos-de-saude` | Estabelecimentos de saúde | CNES |
| `hospitais-e-leitos` | Leitos hospitalares | CNES |

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
                             │ S3 redirect   (fallback: API)
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
