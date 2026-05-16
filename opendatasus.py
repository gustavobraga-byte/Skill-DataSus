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

VERSION = "1.1.0"

import csv
import gzip
import io
import json
import os
import re
import sys
import urllib.request
import zipfile
import argparse
from collections import defaultdict
from datetime import datetime, timezone

OPENDATASUS_URL = "https://dadosabertos.saude.gov.br"
NEXT_DATA_BUILD = "Bbs1i2zf-lNNrT5rwKkbo"

UA = {"User-Agent": "opencode-datasus/1.0"}


def fetch_json(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def listar_datasets():
    """Retorna lista de todos os datasets (paginação automática)."""
    todos = []
    for page in range(1, 8):
        url = f"{OPENDATASUS_URL}/_next/data/{NEXT_DATA_BUILD}/dataset.json?rows=20&page={page}"
        try:
            data = fetch_json(url, timeout=15)
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
    url = f"{OPENDATASUS_URL}/_next/data/{NEXT_DATA_BUILD}/dataset/{name}.json"
    data = fetch_json(url, timeout=15)
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


def _raw_rows(data_bytes):
    """Iterator over text lines from raw bytes (latin-1)."""
    text = data_bytes.decode("latin-1")
    for line in text.splitlines():
        yield line


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


def baixar_csv_stream(url):
    """Baixa CSV (ou CSV dentro de ZIP) do S3, yield linhas como dict."""
    data = _open_url(url)
    reader = csv.reader(
        _raw_rows(data),
        delimiter=";",
    )
    header = [h.strip('"') for h in next(reader)]
    for row in reader:
        yield dict(zip(header, (c.strip('"') for c in row)))


def baixar_json(url):
    """Baixa JSON."""
    return fetch_json(url, timeout=300)


def parse_filter_value(val):
    """Tenta converter valor para número ou booleano."""
    val = val.strip()
    if val.lower() in ("true", "yes", "sim"):
        return "1"
    if val.lower() in ("false", "no", "nao"):
        return "0"
    return val


def match_filter(row, filtros):
    """Verifica se linha satisfaz todos os filtros."""
    for col, val in filtros:
        actual = row.get(col, "").strip()
        val = val.strip()
        if actual != val:
            return False
    return True


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
        metadados, resources = resolver_dataset(args.name)
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
        metadados, resources = resolver_dataset(args.name)
        if not resources:
            print(f"ERRO: Nenhum recurso encontrado para '{args.name}'", file=sys.stderr)
            sys.exit(1)

        if args.recurso is not None:
            if args.recurso < 0 or args.recurso >= len(resources):
                print(f"ERRO: Índice de recurso inválido. Use 0-{len(resources)-1}", file=sys.stderr)
                sys.exit(1)
            recurso = resources[args.recurso]
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

        if fmt == "csv":
            colunas_exibir = None
            if args.colunas:
                colunas_exibir = [c.strip() for c in args.colunas.split(",")]

            grp_vals = defaultdict(int)
            grp_sums = defaultdict(float)
            grp_counts = defaultdict(int)
            total_lines = 0
            filtrados = 0

            for row in baixar_csv_stream(url):
                total_lines += 1
                if total_lines % 500000 == 0:
                    print(f"  Processados: {total_lines:,} registros...", file=sys.stderr)

                if not match_filter(row, filtros):
                    continue

                filtrados += 1

                if args.group:
                    chave = row.get(args.group, "")
                    grp_vals[chave] += 1
                    grp_counts[chave] += 1
                    if args.group_val and args.group_fn in ("sum", "avg", "min", "max"):
                        try:
                            v = float(row.get(args.group_val, "0") or "0")
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
                for row in baixar_csv_stream(url):
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

        elif fmt == "json":
            data = baixar_json(url)
            if isinstance(data, list):
                if args.limit:
                    data = data[:args.limit]
                print(json.dumps(data, indent=2, ensure_ascii=False)[:5000])
            else:
                print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
        else:
            print(f"Formato '{fmt}' não suportado para consulta direta.")
            print(f"URL do recurso: {url}")
            print(f"Baixe manualmente ou use outro formato (CSV preferencial).")


if __name__ == "__main__":
    main()
