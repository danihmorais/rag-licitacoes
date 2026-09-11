from __future__ import annotations

import argparse
from pathlib import Path

import config
from .collector import TRIBUNALS, collect
from .queries import DEFAULT_QUERIES, parse_queries


def collect_batch(tribunals, queries, limit, *, detail=False, with_content=False, output_dir=None):
    output_dir = output_dir or (config.SOURCE_CACHE_DIR / "jurisprudencia")
    output = []
    seen = set()
    for query in queries:
        records = collect(
            tribunals,
            query,
            limit,
            detail=detail,
            with_content=with_content,
            output_dir=output_dir,
        )
        for record in records:
            key = (
                record.tribunal,
                record.numero_processo,
                record.numero_decisao or "",
                record.tipo_decisao or "",
                record.version_sha256 or "",
            )
            if key in seen:
                continue
            seen.add(key)
            output.append(record)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta jurisprudência oficial por consultas temáticas.")
    parser.add_argument("--tribunais", default=",".join(TRIBUNALS))
    parser.add_argument("--query", action="append", default=None)
    parser.add_argument("--limit", type=int, default=config.JURISPRUDENCIA_LIMIT)
    parser.add_argument("--detail", action="store_true")
    parser.add_argument("--with-content", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    tribunals = tuple(item.strip().lower() for item in args.tribunais.split(",") if item.strip())
    unknown = [item for item in tribunals if item not in TRIBUNALS]
    if unknown:
        parser.error("tribunais inválidos: " + ", ".join(unknown))
    queries = tuple(args.query) if args.query else parse_queries(None)
    config.ensure_directories()
    records = collect_batch(
        tribunals,
        queries,
        max(1, args.limit),
        detail=args.detail,
        with_content=args.with_content,
        output_dir=args.output_dir,
    )
    print(f"Consultas: {len(queries)} | Registros únicos: {len(records)}")
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
