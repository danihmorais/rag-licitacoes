from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import config
from .collector import TRIBUNALS, collect, save_record
from .sumulas import collect_sumulas
from .queries import DEFAULT_QUERIES, parse_queries


DLQ_PATH = config.DB_DIR / 'jurisprudencia_dlq.jsonl'


def _write_dlq(*, tribunal, query, stage, error, record=None, path=None):
    target = Path(path or DLQ_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'tribunal': tribunal,
        'query': query,
        'stage': stage,
        'error_type': type(error).__name__,
        'error': str(error),
    }
    if record is not None:
        try:
            payload['record'] = record.to_dict()
        except Exception:
            payload['record'] = {'repr': repr(record)}
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + '\n'
    with target.open('a', encoding='utf-8') as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


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
    dlq_path=None,
    include_sumulas=True,
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
            try:
                records = collect(
                    (tribunal,),
                    query,
                    query_limit,
                    detail=detail,
                    with_content=with_content,
                    output_dir=output_dir,
                    persist=False,
                )
            except Exception as exc:
                failures.add(tribunal)
                _write_dlq(
                    tribunal=tribunal,
                    query=query,
                    stage='collect',
                    error=exc,
                    path=dlq_path,
                )
                continue
            for record in records:
                key = record.document_key
                if key in seen:
                    continue
                seen.add(key)
                try:
                    record.validate()
                except Exception as exc:
                    _write_dlq(
                        tribunal=tribunal,
                        query=query,
                        stage='validate',
                        error=exc,
                        record=record,
                        path=dlq_path,
                    )
                    continue
                output.append(record)
                tribunal_key = record.tribunal.casefold()
                if tribunal_key in counts:
                    counts[tribunal_key] += 1

    sumulas = {"tcu": [], "tcesp": []}
    if include_sumulas:
        try:
            sumulas = collect_sumulas(strict=strict)
        except Exception as exc:
            if strict:
                raise
            print(f"Aviso: coleta de súmulas terminou com falha: {type(exc).__name__}: {exc}")
            sumulas = {"tcu": [], "tcesp": []}
        for tribunal in ("tcu", "tcesp"):
            for record in sumulas.get(tribunal, []):
                key = record.document_key
                if key in seen:
                    continue
                seen.add(key)
                try:
                    record.validate()
                except Exception as exc:
                    _write_dlq(
                        tribunal=tribunal,
                        query="<sumulas>",
                        stage="validate",
                        error=exc,
                        record=record,
                        path=dlq_path,
                    )
                    continue
                output.append(record)

    sumula_save_failures = []
    persisted = []
    for record in output:
        tribunal = record.tribunal.casefold()
        try:
            save_record(record, output_dir)
        except Exception as exc:
            _write_dlq(
                tribunal=tribunal,
                query='<batch-save>',
                stage='save',
                error=exc,
                record=record,
                path=dlq_path,
            )
            if str(record.tipo_decisao or '').strip().casefold() == 'súmula':
                sumula_save_failures.append(tribunal)
            else:
                counts[tribunal] = max(0, counts.get(tribunal, 0) - 1)
            continue
        persisted.append(record)
    output = persisted

    if strict and sumula_save_failures:
        raise RuntimeError('Falhas ao persistir súmulas estruturadas: ' + ', '.join(sorted(set(sumula_save_failures))))

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
    print(f'Súmulas estruturadas: TCU={len(sumulas.get("tcu", []))} | TCESP={len(sumulas.get("tcesp", []))}')
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
    parser.add_argument('--without-sumulas', action='store_false', dest='include_sumulas', help='Não coleta as Súmulas do TCU e do TCESP; útil para health-checks pontuais.')
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
        include_sumulas=args.include_sumulas,
    )
    print(f'Consultas: {len(queries)} | Registros únicos: {len(records)}')
    return 0 if records else 1


if __name__ == '__main__':
    raise SystemExit(main())
