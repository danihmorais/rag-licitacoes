from __future__ import annotations
import hashlib
import json
from pathlib import Path
from config import SETTINGS

ALGORITHM_VERSION = "2026-09-21-recovery-1"

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def current_manifest() -> dict:
    chunking = Path(__file__).resolve().parent / "chunking.py"
    metadata = Path(__file__).resolve().parent / "metadata.py"
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "chunk_size": SETTINGS.chunk_size,
        "chunk_overlap": SETTINGS.chunk_overlap,
        "embedding_model": SETTINGS.embedding_model,
        "collection": SETTINGS.collection,
        "chunking_sha256": _sha(chunking),
        "metadata_sha256": _sha(metadata),
    }

def write_manifest(path: Path | None = None) -> None:
    path = path or (SETTINGS.root / "data" / "index_manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current_manifest(), ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    print(json.dumps(current_manifest(), ensure_ascii=False, indent=2))
