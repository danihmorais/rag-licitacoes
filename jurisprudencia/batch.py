from __future__ import annotations

import argparse
from pathlib import Path

import config
from .collector import TRIBUNALS, collect, save_record
from .queries import DEFAULT_QUERIES, parse_queries


def collect_batch(
    tribunals,
    queries,
    limit,
    *,
    detail=False,
    with_content=False,
    output_dir=None,
    strict=False,
    min_records_per_tribunal=1,
    per_query_limit=25,
):
    output_dir = output_dir or (config.SOURCE_CACHE_DIR / 'jurisprudencia')
    output = []
    seen = set()
    counts = {tribunal: 0 for tribunal in tribunals}
    failures = set()

    if limit < 1:
        raise ValueError('limit deve ser >= 1')
    if min_records_per_tribunal < 1:
        raise ValueError('min_records_per_tribunal deve ser >= 1')
    if min_records_per_tribunal > limit:
        raise ValueError('min_records_per_tribunal não pode exceder limit')
    if per_query_limit < 1:
        raise ValueError('per_query_limit deve ser >= 1')

    for query in queries:
        pending = [tribunal for tribunal in tribunals if counts[tribunal] < limit]
        if not pending:
            break
        for tribunal in pending:
            remaining = limit - counts[tribunal]
            if remaining <= 0:
                continue
            query_limit = min(per_query_limit, remaining)
            records = collect(
                (tribunal,),
                query,
                query_limit,
                detail=detail,
                with_content=with_content,
                output_dir=output_dir,
                persist=False,
            )
            for record in records:
                key = record.document_key
                if key in seen:
                    continue
                seen.add(key)
                output.append(record)
                tribunal_key = record.tribunal.casefold()
                if tribunal_key in counts:
                    counts[tribunal_key] += 1

    for record in output:
        save_record(record, output_dir)

    for tribunal in tribunals:
        if counts.get(tribunal, 0) < min_records_per_tribunal:
            failures.add(tribunal)

    if strict and failures:
        details = ', '.join(
            f'{tribunal}={counts.get(tribunal, 0)}' for tribunal in sorted(failures)
        )
        raise RuntimeError(
            f'Tribunais abaixo do mínimo de {min_records_per_tribunal} registros: {details}'
        )

    print('Registros por tribunal: ' + ', '.join(
        f'{tribunal}={counts.get(tribunal, 0)}' for tribunal in tribunals
    ))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description='Coleta jurisprudência oficial por consultas temáticas.')
    parser.add_argument('--tribunais', default=','.join(TRIBUNALS))
    parser.add_argument('--query', action='append', default=None)
    parser.add_argument('--limit', type=int, default=config.JURISPRUDENCIA_LIMIT)
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--with-content', action='store_true')
    parser.add_argument('--strict', action='store_true', help='Falha se algum tribunal solicitado ficar abaixo do mínimo de registros.')
    parser.add_argument('--min-records-per-tribunal', type=int, default=config.JURISPRUDENCIA_MIN_RECORDS_PER_TRIBUNAL)
    parser.add_argument('--per-query-limit', type=int, default=25, help='Máximo coletado por tribunal em cada consulta temática.')
    parser.add_argument('--output-dir', type=Path, default=None)
    args = parser.parse_args()
    if args.min_records_per_tribunal < 1:
        parser.error('--min-records-per-tribunal deve ser >= 1')
    if args.per_query_limit < 1:
        parser.error('--per-query-limit deve ser >= 1')
    if args.min_records_per_tribunal > max(1, args.limit):
        parser.error('--min-records-per-tribunal não pode exceder --limit')
    tribunals = tuple(item.strip().lower() for item in args.tribunais.split(',') if item.strip())
    unknown = [item for item in tribunals if item not in TRIBUNALS]
    if unknown:
        parser.error('tribunais inválidos: ' + ', '.join(unknown))
    config.ensure_directories()
    queries = tuple(args.query) if args.query else DEFAULT_QUERIES
    records = collect_batch(
        tribunals,
        queries,
        max(1, args.limit),
        detail=args.detail,
        with_content=args.with_content,
        output_dir=args.output_dir,
        strict=args.strict,
        min_records_per_tribunal=args.min_records_per_tribunal,
        per_query_limit=args.per_query_limit,
    )
    print(f'Consultas: {len(queries)} | Registros únicos: {len(records)}')
    return 0 if records else 1


if __name__ == '__main__':
    raise SystemExit(main())
