#!/usr/bin/env python3
"""OpenDataSUS — Dados Abertos do SUS

Acessa 101 datasets oficiais do Ministério da Saúde via OpenDataSUS.
Dados armazenados em bucket S3 público da AWS (sem autenticação).

Uso:
  opendatasus.py list                      # Lista todos os datasets
  opendatasus.py info <dataset>            # Detalhes de um dataset
  opendatasus.py query <dataset>           # Consulta dados (CSV preferencial)

Requer apenas Python 3 (stdlib). Dados oficiais — sem fabricação.
"""

VERSION = "1.2.0"

import csv
import io
import json
import re
import sys
import time
import urllib.request
import urllib.error
from urllib.error import HTTPError, URLError
import zipfile
import argparse
from collections import defaultdict

OPENDATASUS_URL = "https://dadosabertos.saude.gov.br"
# Nuvem de segurança: o buildId do Next.js muda quando o site é recompilado.
# Função que o detecta dinamicamente e usa este valor como fallback.
NEXT_DATA_BUILD = "Hf5EbSN9hp8IRkcbPMMPa"

UA = {"User-Agent": "opencode-datasus/1.0"}


def fetch_json(url, timeout=45, retries=3):
    """Faz GET e retorna JSON, com retry simples em falhas/timeouts."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * attempt)
    raise last_err


_CACHE_BUILD_ID = None


def get_build_id(timeout=20):
    """Obtém dinamicamente o buildId (sufixo de cache) do site Next.js.

    O buildId muda quando o OpenDataSUS é recompilado; descobri-lo em
    tempo de execução evita que o script pare de funcionar quando o
    hash hardcoded expira (o que já ocorreu e causou HTTP 404).
    """
    global _CACHE_BUILD_ID
    if _CACHE_BUILD_ID:
        return _CACHE_BUILD_ID
    try:
        req = urllib.request.Request(f"{OPENDATASUS_URL}/dataset/sim", headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            html = r.read().decode("utf-8", "ignore")
        m = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
        if m:
            _CACHE_BUILD_ID = m.group(1)
            print(f"[opendatasus] buildId detectado: {_CACHE_BUILD_ID}", file=sys.stderr)
            return _CACHE_BUILD_ID
    except Exception as e:
        print(f"[opendatasus] aviso: falha ao detectar buildId ({e}); usando fallback",
              file=sys.stderr)
    return NEXT_DATA_BUILD


def listar_datasets():
    """Retorna lista de todos os datasets (paginação automática)."""
    todos = []
    for page in range(1, 8):
        url = f"{OPENDATASUS_URL}/_next/data/{get_build_id()}/dataset.json?rows=20&page={page}"
        try:
            data = fetch_json(url)
            pkgs = data["pageProps"]["packages"]
            if not pkgs:
                break
            for p in pkgs:
                todos.append({
                    "name": p["name"],
                    "title": p["title"],
                    "formats": p.get("formats", []),
                    "groups": [g["display_name"] for g in p.get("groups", [])],
                    "notes": (p.get("notes") or "")[:200],
                })
        except Exception:
            break
    return todos


def resolver_dataset(name):
    """Obtém metadados + recursos de um dataset pelo nome."""
    url = f"{OPENDATASUS_URL}/_next/data/{get_build_id()}/dataset/{name}.json"
    data = fetch_json(url)
    pp = data["pageProps"]

    metadados = {
        "name": pp.get("name", name),
        "title": pp.get("title", ""),
        "notes": (pp.get("notes") or "")[:500],
        "author": pp.get("author"),
        "license_title": pp.get("license_title"),
        "metadata_created": pp.get("metadata_created"),
        "metadata_modified": pp.get("metadata_modified"),
    }

    resources = []
    for r in pp.get("resources", []):
        res = {
            "name": r.get("name"),
            "format": (r.get("format") or "").lower(),
            "url": r.get("url"),
            "description": (r.get("description") or "")[:200],
        }
        if res["url"] and res["format"]:
            resources.append(res)

    return metadados, resources


FORMAT_PREFERENCE = {"csv": 0, "json": 1, "parquet": 2, "xml": 3}


def melhor_recurso(resources):
    """Escolhe o melhor recurso para consulta (CSV > JSON > Parquet > XML)."""
    csvs = [r for r in resources if r["format"] == "csv"]
    if csvs:
        return csvs[-1]
    json_res = [r for r in resources if r["format"] == "json"]
    if json_res:
        return json_res[-1]
    return resources[-1] if resources else None


def _open_url(url):
    """Abre URL e retorna (bytes, is_zip)."""
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    is_zip = url.lower().endswith(".zip") or data[:2] == b"PK"
    if is_zip:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            csv_name = next((n for n in names if n.endswith(".csv")), names[0])
            data = z.read(csv_name)
    return data


def _detect_delimiter(text):
    """Detecta delimitador de CSV de forma robusta (';' ou ',').

    O csv.Sniffer do Python é instável: para certos arquivos (ex.: SINAN/Dengue)
    ele falha ("Could not determine delimiter") dependendo do tamanho da amostra
    usada. Para contornar isso, testamos o Sniffer com múltiplas amostras e,
    se todas falharem, usamos uma heurística de contagem no primeiro bloco de
    linhas. Por fim, validamos o resultado verificando se o cabeçalho foi quebrado
    em >1 coluna; se não, tentamos o outro delimitador.
    """
    # 1) Sniffer com múltiplas amostras (pega arquivos com layout irregular)
    linhas_naoagric = [ln for ln in text.splitlines() if ln.strip()]
    if not linhas_naoagric:
        return ";"
    for amostra in (1024, 4096, 16384, len(text)):
        fatia = text[:amostra]
        try:
            d = csv.Sniffer().sniff(fatia, delimiters=";,")
            # valida: quebrou o cabeçalho em mais de uma coluna?
            probe = next((ln for ln in linhas_naoagric if d.delimiter in ln), None)
            if probe is not None and len(probe.split(d.delimiter)) > 1:
                return d.delimiter
        except csv.Error:
            continue

    # 2) Heurística de contagem na primeira linha coroada por cada delimitador
    cab = linhas_naoagric[0]
    n_virg = cab.count(",")
    n_pv = cab.count(";")
    if n_virg > n_pv:
        return ","
    return ";"


def baixar_csv_stream(url):
    """Baixa CSV (ou CSV dentro de ZIP) do S3, yield linhas como dict.

    Detecta automaticamente o delimitador (';' ou ',') pois os datasets
    do OpenDataSUS misturam ambos os formatos (ex.: SIM usa ';', SINAN/Dengue
    e RIPSA usam ','). Também lida com BOM e aspas.
    """
    data = _open_url(url)
    text = data.decode("utf-8-sig", errors="replace")
    delim = _detect_delimiter(text)

    lines = text.splitlines()
    reader = csv.reader(lines, delimiter=delim)
    # Pula eventuais linhas em branco antes do cabeçalho
    header = None
    for row in reader:
        if not any(c.strip() for c in row):
            continue
        header = [h.strip('"') for h in row]
        break
    if header is None:
        return
    for row in reader:
        if not any(c.strip() for c in row):
            continue
        yield dict(zip(header, (c.strip('"') for c in row)))


def baixar_json(url):
    """Baixa JSON."""
    return fetch_json(url, timeout=300)


# Base da API de Dados Abertos do SUS (fonte oficial alternativa ao bucket S3)
APIDADOSABERTOS_BASE = "https://apidadosabertos.saude.gov.br"

_SWAGGER_PATHS = None


def _swagger_paths(timeout=30):
    """Retorna lista de paths reais da API (ex.: '/vigilancia-e-meio-ambiente/...').

    Baixa o spec OpenAPI uma vez e o cacheia em memória.
    """
    global _SWAGGER_PATHS
    if _SWAGGER_PATHS is not None:
        return _SWAGGER_PATHS
    try:
        req = urllib.request.Request(f"{APIDADOSABERTOS_BASE}/static/swagger.json", headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            spec = json.loads(r.read())
        _SWAGGER_PATHS = list(spec.get("paths", {}).keys())
    except Exception:
        _SWAGGER_PATHS = []
    return _SWAGGER_PATHS


def api_rota_do_recurso(resource, timeout=30):
    """Extrai a rota real da API a partir da URL do recurso (fragmento Swagger).

    O link tem formato '#/Tag/get_rota_com_underlines'. Como o path real usa
    hífens e '/' (ex.: '/vigilancia-e-meio-ambiente/sistema-de-informacao-sobre-
    mortalidade'), normalizamos os paths reais e buscamos match com o fragmento.
    """
    url = resource.get("url", "")
    if APIDADOSABERTOS_BASE not in url:
        return None
    # Fragmento após o último '#/' -> ex.: 'get_vigilancia_...'
    frag = url.split("#/")[-1].strip()
    m = re.search(r"(get|post|put|delete)_(.*)$", frag)
    if not m:
        return None
    operacao, resto = m.group(1), m.group(2)
    # Chave normalizada esperada do fragmento
    alvo = f"{operacao}_{resto}".replace("-", "_").lower()
    paths = _swagger_paths(timeout=timeout)
    # 1) match exato por normalização (robusto)
    for p in paths:
        norm = ("get_" + p.strip("/")).replace("/", "_").replace("-", "_").lower()
        if norm == alvo:
            return p
    # 2) fallback: substring do resto com hífens
    alvo_hi = resto.replace("_", "-").lower()
    for p in paths:
        if alvo_hi in p.lower():
            return p
    # 3) último fallback: converte underscores em hífens e prefixa '/'
    return "/" + resto.replace("_", "-")


def encontra_recurso_api(resources):
    """Retorna o recurso de API (formato 'API' com URL apidadosabertos), se houver."""
    for r in resources:
        if r.get("format") == "api" and APIDADOSABERTOS_BASE in r.get("url", ""):
            return r
    return None


def api_fetch_rows(rota, limit=1000, offset=0):
    """Busca registros da API oficial. Retorna (lista de dicts, total_estimado ou None).

    Tenta CVS (Accept: text/csv) primeiro (mais leve), com fallback para JSON.
    """
    url = f"{APIDADOSABERTOS_BASE}{rota}?limit={limit}&offset={offset}"
    # --- tenta CSV ---
    try:
        req = urllib.request.Request(url, headers={**UA, "Accept": "text/csv"})
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
        text = raw.decode("utf-8-sig", errors="replace")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) >= 2:
            reader = csv.reader(lines, delimiter=";")
            header = [h.strip('"').strip() for h in next(reader)]
            rows = []
            for row in reader:
                rows.append(dict(zip(header, (c.strip('"') for c in row))))
            return rows, len(rows)
    except urllib.error.HTTPError:
        # sem suporte CSV -> tenta JSON
        pass
    except Exception:
        pass
    # --- fallback JSON ---
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        payload = json.loads(r.read())
    # O payload é um dict cuja chave é o nome da entidade (ex.: 'sim' -> lista)
    rows = payload
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list):
                rows = v
                break
    return rows, len(rows) if isinstance(rows, list) else None


def parse_filter_value(val):
    """Tenta converter valor para número ou booleano."""
    val = val.strip()
    if val.lower() in ("true", "yes", "sim"):
        return "1"
    if val.lower() in ("false", "no", "nao"):
        return "0"
    return val


def _get_col(row, name):
    """Busca valor de coluna de forma case-insensitive.

    Os CSVs do OpenDataSUS usam nomes de colunas inconsistentes entre fontes
    (ex.: SIM usa 'SEXO' em caixa alta no CSV, mas 'sexo' na API).
    """
    if name in row:
        return row[name]
    lname = name.lower()
    for k, v in row.items():
        if k.lower() == lname:
            return v
    return row.get(name, "")


def match_filter(row, filtros):
    """Verifica se linha satisfaz todos os filtros (case-insensitive por coluna)."""
    for col, val in filtros:
        actual = _get_col(row, col).strip()
        val = val.strip()
        if actual != val:
            return False
    return True


def _url_variante_csv(url):
    """Retorna variante do URL com '/csv/' inserido antes do nome do arquivo
    (padrão atual do bucket do MS). Ex.:
      .../SIM/Mortalidade_Geral_2026_csv.zip
      -> .../SIM/csv/Mortalidade_Geral_2026_csv.zip
    Retorna a própria URL se não houver o que mudar.
    """
    if "/csv/" in url.split("?")[0]:
        return url
    base = url.split("/")
    nome = base[-1]
    pasta = "/".join(base[:-1])
    return f"{pasta}/csv/{nome}"


def iter_csv_com_fallback(url, resources, max_records=200000):
    """Itera linhas de um CSV do S3 com robusters em camadas:
    1) tenta a URL original;
    2) se falhar (403/404), tenta a variante com '/csv' (mudança estrutural do bucket);
    3) se ainda falhar, usa a API oficial de Dados Abertos como fallback.
    'max_records' limita o volume consultado via API.
    """
    tentativas = [url]
    variante = _url_variante_csv(url)
    if variante != url:
        tentativas.append(variante)

    ultimo_erro = None
    for u in tentativas:
        try:
            for row in baixar_csv_stream(u):
                yield row
            return
        except (HTTPError, URLError, OSError, ValueError) as e:
            ultimo_erro = e
            continue

    api_rec = encontra_recurso_api(resources)
    if api_rec is None:
        raise ultimo_erro
    rota = api_rota_do_recurso(api_rec)
    if not rota:
        raise ultimo_erro
    print(f"[fallback] S3 indisponível ({type(ultimo_erro).__name__}); "
          f"usando API oficial {rota}", file=sys.stderr)
    offset = 0
    while offset < max_records:
        rows, n = api_fetch_rows(rota, limit=1000, offset=offset)
        if not rows:
            break
        for row in rows:
            yield row
        if n < 1000:
            break
        offset += 1000


def iter_registros(recurso, resources):
    """Fonte unificada de linhas a partir de um recurso (CSV do S3 com fallback API)."""
    fmt = recurso["format"]
    if fmt == "api":
        rota = api_rota_do_recurso(recurso)
        if not rota:
            raise ValueError(f"Não foi possível extrair rota da API: {recurso['url']}")
        offset = 0
        while True:
            rows, n = api_fetch_rows(rota, limit=1000, offset=offset)
            if not rows:
                break
            for row in rows:
                yield row
            if n < 1000:
                break
            offset += 1000
    elif fmt == "csv":
        yield from iter_csv_com_fallback(recurso["url"], resources)
    elif fmt == "json":
        data = baixar_json(recurso["url"])
        if isinstance(data, list):
            for row in data:
                yield row if isinstance(row, dict) else {recurso["name"]: row}
        elif isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    for row in v:
                        yield row if isinstance(row, dict) else {recurso["name"]: row}
                    break
    else:
        raise ValueError(f"Formato '{fmt}' não suportado para consulta via API/CSV")


def _resolver_dataset_amigavel(name):
    """Resolve um dataset convertendo erros de acesso (404/500 do portal,
    rede) numa mensagem clara de 'não encontrado' em vez de um traceback cru."""
    try:
        return resolver_dataset(name)
    except HTTPError as e:
        if e.code in (404, 500):
            print(f"ERRO: Dataset '{name}' não encontrado no OpenDataSUS "
                  f"(HTTP {e.code}). Verifique o nome com 'list'.",
                  file=sys.stderr)
        else:
            print(f"ERRO de acesso ao portal OpenDataSUS (HTTP {e.code}): {e}",
                  file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"ERRO de rede ao consultar o OpenDataSUS: {e.reason}",
              file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="OpenDataSUS - Dados Abertos do SUS",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="cmd")

    # list
    p_list = sub.add_parser("list", help="Listar datasets disponíveis")
    p_list.add_argument("--grupo", "-g", help="Filtrar por categoria (ex: Vigilância)")
    p_list.add_argument("--search", "-s", help="Buscar por termo no título/descrição")
    p_list.add_argument("--formato", "-f", help="Filtrar por formato (CSV, JSON, API)")
    p_list.add_argument("--json", action="store_true", help="Saída JSON")

    # info
    p_info = sub.add_parser("info", help="Detalhes de um dataset")
    p_info.add_argument("name", help="Nome do dataset (ex: srag-2019-a-2026)")

    # query
    p_query = sub.add_parser("query", help="Consultar dados de um dataset")
    p_query.add_argument("name", help="Nome do dataset")
    p_query.add_argument("--recurso", "-r", type=int, default=None,
                         help="Índice do recurso (0=primeiro, -1=último). Default: melhor formato")
    p_query.add_argument("--filter", "-f", action="append", default=[],
                         help="Filtro: COLUNA=VALOR (pode repetir)")
    p_query.add_argument("--group", "-g", help="Agrupar por coluna")
    p_query.add_argument("--group-fn", default="count",
                         help="Função de agregação: count (padrão), sum, avg, min, max")
    p_query.add_argument("--group-val", default=None,
                         help="Coluna para agregar (para sum/avg/min/max)")
    p_query.add_argument("--limit", "-l", type=int, default=0,
                         help="Limitar linhas processadas")
    p_query.add_argument("--colunas", "-c", help="Colunas para exibir (separadas por vírgula)")
    p_query.add_argument("--sample", action="store_true",
                         help="Apenas amostra (10 primeiras linhas)")
    p_query.add_argument("--json", action="store_true", help="Saída JSON")

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return

    # ---- list ----
    if args.cmd == "list":
        datasets = listar_datasets()
        grupo = (args.grupo or "").lower()
        search = (args.search or "").lower()
        formato = (args.formato or "").lower()

        import unicodedata
        def _norm(s):
            return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

        grupo_norm = _norm(grupo) if grupo else ""
        search_norm = _norm(search) if search else ""

        if grupo:
            datasets = [d for d in datasets if any(
                grupo_norm in _norm(g) for g in d["groups"]
            )]
        if search:
            datasets = [d for d in datasets
                        if search_norm in _norm(d["title"])
                        or search_norm in _norm(d.get("notes", ""))]
        if formato:
            datasets = [d for d in datasets
                        if formato in [f.lower() for f in d["formats"]]]

        if args.json:
            print(json.dumps(datasets, indent=2, ensure_ascii=False))
            return

        grupos_disponiveis = sorted(set(
            g for d in datasets for g in d["groups"]
        ))
        formatos_disponiveis = sorted(set(
            f for d in datasets for f in d["formats"]
        ))

        print(f"{'='*80}")
        print(f"OPENDATASUS — Catálogo de Dados ({len(datasets)} datasets)")
        print(f"{'='*80}")

        if grupos_disponiveis:
            print(f"Grupos: {', '.join(grupos_disponiveis)}")
        if formatos_disponiveis:
            print(f"Formatos: {', '.join(formatos_disponiveis)}")
        print()

        for d in datasets:
            grupos = ", ".join(d["groups"]) if d["groups"] else "—"
            formatos = ", ".join(sorted(set(d["formats"])))
            print(f"  {d['name']}")
            print(f"    {d['title']}")
            print(f"    Grupos: {grupos}")
            print(f"    Formatos: {formatos}")
            print()

    # ---- info ----
    elif args.cmd == "info":
        metadados, resources = _resolver_dataset_amigavel(args.name)
        print(f"{'='*70}")
        print(f"DATASET: {metadados['name']}")
        print(f"{'='*70}")
        print(f"  Título: {metadados['title']}")
        print(f"  Autor: {metadados.get('author', '—')}")
        print(f"  Licença: {metadados.get('license_title', '—')}")
        print(f"  Criado: {metadados.get('metadata_created', '—')}")
        print(f"  Atualizado: {metadados.get('metadata_modified', '—')}")
        print(f"  Descrição: {metadados.get('notes', '—')[:300]}")
        print()
        print(f"  Recursos ({len(resources)}):")
        for i, r in enumerate(resources):
            print(f"  [{i}] {r['format'].upper():<8} {r['name']}")
            print(f"       {r['url']}")

    # ---- query ----
    elif args.cmd == "query":
        metadados, resources = _resolver_dataset_amigavel(args.name)
        if not resources:
            print(f"ERRO: Nenhum recurso encontrado para '{args.name}'", file=sys.stderr)
            sys.exit(1)

        if args.recurso is not None:
            idx = args.recurso if args.recurso >= 0 else len(resources) + args.recurso
            if idx < 0 or idx >= len(resources):
                print(f"ERRO: Índice de recurso inválido. Use 0-{len(resources)-1} "
                      f"(ou negativo, ex: -1=último)", file=sys.stderr)
                sys.exit(1)
            recurso = resources[idx]
        else:
            recurso = melhor_recurso(resources)
            if not recurso:
                print("ERRO: Nenhum recurso adequado para consulta", file=sys.stderr)
                sys.exit(1)

        if args.sample:
            args.limit = 10

        # Parse filters
        filtros = []
        for f in args.filter:
            if "=" not in f:
                print(f"ERRO: Filtro inválido: '{f}'. Use COLUNA=VALOR", file=sys.stderr)
                sys.exit(1)
            col, val = f.split("=", 1)
            filtros.append((col.strip(), val.strip()))

        fmt = recurso["format"]
        url = recurso["url"]

        print(f"Dataset: {metadados['title']}", file=sys.stderr)
        print(f"Recurso: {recurso['name']}", file=sys.stderr)
        print(f"Formato: {fmt.upper()}", file=sys.stderr)
        print(f"URL: {url}", file=sys.stderr)
        print(f"Fonte: Dados oficiais do Ministério da Saúde (OpenDataSUS)", file=sys.stderr)
        print(f"Atualizado: {metadados.get('metadata_modified', 'desconhecida')}", file=sys.stderr)
        print(file=sys.stderr)

        if fmt in ("csv", "api", "json"):
            colunas_exibir = None
            if args.colunas:
                colunas_exibir = [c.strip() for c in args.colunas.split(",")]

            grp_vals = defaultdict(int)
            grp_sums = defaultdict(float)
            grp_counts = defaultdict(int)
            total_lines = 0
            filtrados = 0

            try:
                for row in iter_registros(recurso, resources):
                    total_lines += 1
                    if total_lines % 500000 == 0:
                        print(f"  Processados: {total_lines:,} registros...", file=sys.stderr)

                    if not match_filter(row, filtros):
                        continue

                    filtrados += 1

                    if args.group:
                        chave = _get_col(row, args.group)
                        grp_vals[chave] += 1
                        grp_counts[chave] += 1
                        if args.group_val and args.group_fn in ("sum", "avg", "min", "max"):
                            try:
                                v = float(_get_col(row, args.group_val) or "0")
                                grp_sums[chave] += v
                                if args.group_fn == "min":
                                    if chave not in grp_sums:
                                        grp_sums[chave] = v
                                    else:
                                        grp_sums[chave] = min(grp_sums[chave], v)
                                if args.group_fn == "max":
                                    if chave not in grp_sums:
                                        grp_sums[chave] = v
                                    else:
                                        grp_sums[chave] = max(grp_sums[chave], v)
                            except (ValueError, TypeError):
                                pass

                    if args.limit and filtrados >= args.limit:
                        break
            except HTTPError as e:
                print(f"\nERRO de acesso à fonte de dados: {e}", file=sys.stderr)
                print("Não foi possível obter os dados nesta fonte. "
                      "Verifique se o bucket/API está acessível ou tente outro recurso.",
                      file=sys.stderr)
                sys.exit(1)
            except URLError as e:
                print(f"\nERRO de rede ao acessar a fonte: {e.reason}", file=sys.stderr)
                sys.exit(1)

            print()
            print(f"{'='*60}")
            print(f"RESULTADOS — {metadados['title']}")
            print(f"{'='*60}")
            print(f"Total de registros: {total_lines:,}")
            print(f"Após filtros: {filtrados:,}")

            if not filtros and not args.group and not args.sample:
                print()
                print("Dica: Use --filter para filtrar, --group para agrupar,")
                print("      --sample para amostra, ou --limit para limitar.")
                print()

            if args.group:
                print()
                print(f"Agrupado por: {args.group}")
                print(f"{'-'*40}")
                if args.group_fn == "count":
                    ordenado = sorted(grp_vals.items(), key=lambda x: -x[1])
                    for chave, count in ordenado[:50]:
                        label = chave if chave else "(vazio)"
                        print(f"  {label:<30} {count:>8,}")
                    if len(ordenado) > 50:
                        print(f"  ... mais {len(ordenado)-50} grupos")
                    print(f"{'-'*40}")
                    print(f"  {'Total':<30} {filtrados:>8,}")
                elif args.group_fn in ("sum", "avg", "min", "max"):
                    ordenado = sorted(grp_vals.items(), key=lambda x: -x[1])
                    for chave, count in ordenado[:50]:
                        label = chave if chave else "(vazio)"
                        if args.group_fn == "avg":
                            val = grp_sums[chave] / grp_counts[chave] if grp_counts[chave] else 0
                        else:
                            val = grp_sums.get(chave, 0)
                        print(f"  {label:<30} {val:>12,.2f}")
                    print(f"{'-'*40}")

            if not args.group and args.sample:
                print()
                print(f"Amostra (primeiros {filtrados} registros):")
                grp_vals = defaultdict(int)
                for row in iter_registros(recurso, resources):
                    if not match_filter(row, filtros):
                        continue
                    if colunas_exibir:
                        for col in colunas_exibir:
                            val = row.get(col, "")
                            print(f"  {col}: {val[:200]}")
                    else:
                        non_empty = [(k, v) for k, v in row.items() if v.strip()]
                        for col, val in non_empty[:15]:
                            print(f"  {col}: {val[:200]}")
                    print(f"  {'-'*30}")
                    grp_vals["_sample"] += 1
                    if grp_vals["_sample"] >= 5:
                        break

        else:
            print(f"Formato '{fmt}' não suportado para consulta via CSV/API/JSON.")
            print(f"URL do recurso: {url}")
            print(f"Baixe manualmente ou use outro formato (CSV/API preferencial).")


if __name__ == "__main__":
    main()
