from __future__ import annotations
import argparse
import json
from pathlib import Path
from .collector import collect
from .queries import QUERIES

def collect_batch(tribunals: list[str], limit: int, output: Path) -> int:
    records = []
    for tribunal in tribunals:
        for query in QUERIES["licitacoes"]:
            for rec in collect(tribunal, query, limit=limit):
                records.append(rec.to_dict())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(records)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tribunals", nargs="+", default=["TCU","TCESP","STJ","STF"])
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--output", type=Path, default=Path("data/jurisprudencia/records.json"))
    args = p.parse_args()
    n = collect_batch(args.tribunals, args.limit, args.output)
    print(f"records={n} output={args.output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
