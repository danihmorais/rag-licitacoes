import argparse
import datetime
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from fastembed import SparseTextEmbedding
from pypdf import PdfReader
from qdrant_client import models

import config
from index_manifest import read_manifest, write_manifest
from metadata import embedding_metadata_prefix, extract_metadata
from chunking import CHUNKING_VERSION, build_structural_chunks
from embedding_utils import validate_embedding_inputs
from dense_embeddings import create_dense_embedding

PAYLOAD_INDEX_TYPES = {
    'keyword': models.PayloadSchemaType.KEYWORD,
    'integer': models.PayloadSchemaType.INTEGER,
    'bool': models.PayloadSchemaType.BOOL,
}

PAGE_BREAK = '\f'
CACHE_PATH = config.DB_DIR / 'ingest_cache.json'
CACHE_VERSION = 1
LEGACY_CACHE_VERSIONS = set()


def sync_sources():
    if not config.RAG_SYNC_SOURCES:
        return
    script = Path(__file__).parent / 'scripts' / 'sync_sources.py'
    result = subprocess.run(
        [sys.executable, str(script), '--strict'],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            'Sincronização de fontes jurídicas incompleta. Corrija as fontes rejeitadas antes de indexar; '
            'o cache anterior foi preservado onde aplicável.'
        )


def sync_jurisprudencia():
    if not config.RAG_SYNC_JURISPRUDENCIA:
        return
    if config.JURISPRUDENCIA_QUERY:
        command = [
            sys.executable,
            '-m',
            'jurisprudencia.collector',
            '--query',
            config.JURISPRUDENCIA_QUERY,
            '--limit',
            str(config.JURISPRUDENCIA_LIMIT),
        ]
    else:
        command = [
            sys.executable,
            '-m',
            'jurisprudencia.batch',
            '--limit',
            str(config.JURISPRUDENCIA_LIMIT),
        ]
        for query in config.JURISPRUDENCIA_QUERIES:
            command.extend(['--query', query])
    if config.JURISPRUDENCIA_STRICT:
        command.append('--strict')
    if config.JURISPRUDENCIA_DETAIL:
        command.append('--detail')
    if config.JURISPRUDENCIA_WITH_CONTENT:
        command.append('--with-content')
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        if config.JURISPRUDENCIA_STRICT:
            raise RuntimeError(
                'Sincronização de jurisprudência incompleta. Corrija as fontes jurisprudenciais antes de indexar; '
                'o cache anterior foi preservado onde aplicável.'
            )
        print('Aviso: coleta de jurisprudência terminou sem novos registros; cache anterior será preservado.')


def load_documents():
    files = sorted(config.PDFS_DIR.glob('*.pdf')) + sorted(config.SOURCE_CACHE_DIR.rglob('*.txt'))
    if not files:
        print(f'Nenhum documento em {config.PDFS_DIR} nem em {config.SOURCE_CACHE_DIR}.')
        sys.exit(1)
    return files


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata_fingerprint_base():
    digest = hashlib.sha256()
    metadata_path = Path(__file__).with_name('metadata.py')
    digest.update(b'metadata.py\0')
    digest.update(metadata_path.read_bytes())
    digest.update(b'chunking_version\0')
    digest.update(str(CHUNKING_VERSION).encode('ascii'))
    config_values = (
        config.OCR_ENABLED,
        config.OCR_REQUIRED,
        config.OCR_MIN_NATIVE_CHARS_PER_PAGE,
        config.OCR_MIN_NATIVE_CONFIDENCE,
        config.OCR_DPI,
        config.OCR_LANGUAGE,
    )
    digest.update(
        json.dumps(config_values, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    )
    return digest


def metadata_fingerprint(document, *, base=None):
    digest = (base or _metadata_fingerprint_base()).copy()
    sidecar = document.with_suffix('.json')
    if sidecar.exists():
        digest.update(b'sidecar.json\0')
        digest.update(sidecar.read_bytes())
    return digest.hexdigest()


def _cache_entry_matches_index(entry, digest, indexed_count):
    return (
        isinstance(entry, dict)
        and entry.get('sha256') == digest
        and int(entry.get('chunks') or 0) == indexed_count
        and indexed_count > 0
    )


def cache_entry_is_valid(entry, digest, metadata_digest, indexed_count):
    return (
        _cache_entry_matches_index(entry, digest, indexed_count)
        and int(entry.get('_cache_version') or CACHE_VERSION) == CACHE_VERSION
        and entry.get('metadata_fingerprint') == metadata_digest
    )


def read_cache():
    if not CACHE_PATH.exists():
        return {}
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f'Aviso: cache de ingestão inválido; reindexação será feita: {exc}')
        return {}
    version = payload.get('version')
    if version != CACHE_VERSION and version not in LEGACY_CACHE_VERSIONS:
        return {}
    if not isinstance(payload.get('documents'), dict):
        return {}

    documents = {}
    for name, entry in payload['documents'].items():
        if isinstance(entry, dict) and version in LEGACY_CACHE_VERSIONS:
            migrated = dict(entry)
            migrated['_cache_version'] = int(version)
            documents[name] = migrated
        else:
            documents[name] = entry
    return documents


def write_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    clean_documents = {}
    for name, entry in cache.items():
        if isinstance(entry, dict):
            clean = dict(entry)
            clean.pop('_cache_version', None)
            clean_documents[name] = clean
        else:
            clean_documents[name] = entry

    fd, temp_name = tempfile.mkstemp(prefix=f'.{CACHE_PATH.name}.', suffix='.tmp', dir=CACHE_PATH.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump({'version': CACHE_VERSION, 'documents': clean_documents}, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, CACHE_PATH)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _native_extraction_confidence(text):
    text = str(text or '')
    if not text.strip():
        return 0.0
    non_whitespace = len(''.join(text.split()))
    visible = sum(character.isprintable() or character in '\r\n\t' for character in text)
    visible_ratio = visible / max(1, len(text))
    alpha_numeric = sum(character.isalnum() for character in text)
    alpha_ratio = alpha_numeric / max(1, non_whitespace)
    replacement_ratio = text.count('\ufffd') / max(1, len(text))
    density = min(1.0, non_whitespace / 180.0)
    confidence = visible_ratio * min(1.0, alpha_ratio * 1.15) * density * (1.0 - replacement_ratio)
    return round(max(0.0, min(1.0, confidence)), 4)


def _sanitize_extracted_page_text(text):
    text = str(text or '')
    if not text.strip():
        return ''

    def is_page_noise(line):
        token = re.sub(r'\s+', ' ', line).strip()
        if not token:
            return True
        # A normative heading is legal content. It may resemble a repeated PDF
        # header, but deciding that needs cross-page evidence, not this local
        # sanitizer alone.
        if re.match(r'(?i)^(?:LEI|DECRETO|DECRETO-LEI|PORTARIA|EMENDA|MEDIDA)\b', token):
            return False
        if re.fullmatch(r'(?i)(?:P[AÁ]GINA|PAGINA|PAGE)\s*[:\-]?\s*\d+[A-Za-z-]*', token):
            return True
        if re.fullmatch(r'(?i)(?:LEI|DECRETO|DECRETO-LEI|PORTARIA|RESOLUÇÃO|RESOLUCAO|INSTRUÇÃO|INSTRUCAO|EMENDA|MEDIDA|REGULAMENTO|NORMA)\b.*', token):
            return True
        if re.fullmatch(r'\d{1,5}(?:\s*[-/]\s*\d+)?', token):
            return True
        return False

    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines()]
    while lines and is_page_noise(lines[0]):
        lines.pop(0)
    while lines and is_page_noise(lines[-1]):
        lines.pop()

    if not lines:
        return ''

    deduped = []
    for line in lines:
        if line and deduped and line == deduped[-1] and is_page_noise(line):
            continue
        deduped.append(line)

    cleaned = '\n'.join(deduped)
    cleaned = re.sub(r'(?<=\w)-\s+(?=\w)', '', cleaned)
    cleaned = re.sub(r'(?m)^(?:P[AÁ]GINA|PAGINA|PAGE)\s*[:\-]?\s*\d+[A-Za-z-]*\s*$', '', cleaned, flags=re.I)
    cleaned = re.sub(r'(?m)^\d{1,5}(?:\s*[-/]\s*\d+)?\s*$', '', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned


def _remove_repeated_page_noise(records):
    """Remove apenas cabeçalhos/rodapés não normativos repetidos nas bordas de páginas."""
    if len(records) < 2:
        return records

    edge_counts = {}
    for record in records:
        lines = [line.strip() for line in str(record.get('text') or '').splitlines() if line.strip()]
        if not lines:
            continue
        for line in {lines[0], lines[-1]}:
            normalized = re.sub(r'\s+', ' ', line).strip().casefold()
            edge_counts[normalized] = edge_counts.get(normalized, 0) + 1

    def removable(line):
        token = re.sub(r'\s+', ' ', line).strip()
        normalized = token.casefold()
        if edge_counts.get(normalized, 0) < 2:
            return False
        # Preservamos linhas que podem ser conteúdo normativo mesmo quando
        # aparecem repetidas; repetição sozinha não autoriza apagar evidência.
        if re.match(
            r'(?i)^(?:LEI|DECRETO|DECRETO-LEI|PORTARIA|RESOLUÇÃO|RESOLUCAO|'
            r'INSTRUÇÃO|INSTRUCAO|EMENDA|MEDIDA|ART(?:IGO)?\b|§)',
            token,
        ):
            return False
        if re.match(r'(?i)^(?:CAP[IÍ]TULO|T[IÍ]TULO|SE[CÇ][AÃ]O|SUBSE[CÇ][AÃ]O|PARTE|LIVRO|ANEXO)\b', token):
            return False
        if len(token) > 180:
            return False
        return True

    for record in records:
        lines = [line.strip() for line in str(record.get('text') or '').splitlines() if line.strip()]
        while lines and removable(lines[0]):
            lines.pop(0)
        while lines and removable(lines[-1]):
            lines.pop()
        record['text'] = '\n'.join(lines).strip()
    return records


def _ocr_page(pdf_document, page_number):
    try:
        import pymupdf
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            'OCR necessário, mas PyMuPDF/pytesseract não estão instalados. '
            'Instale as dependências do projeto e o Tesseract OCR.'
        ) from exc
    page = pdf_document.load_page(page_number - 1)
    scale = config.OCR_DPI / 72.0
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    image = Image.frombytes('RGB', [pixmap.width, pixmap.height], pixmap.samples)
    ocr_config = '--psm 6'
    text = pytesseract.image_to_string(image, lang=config.OCR_LANGUAGE, config=ocr_config) or ''
    data = pytesseract.image_to_data(
        image,
        lang=config.OCR_LANGUAGE,
        config=ocr_config,
        output_type=pytesseract.Output.DICT,
    )
    confidences = []
    for raw_conf in data.get('conf', []):
        try:
            confidence = float(raw_conf)
        except (TypeError, ValueError):
            continue
        if confidence >= 0:
            confidences.append(confidence / 100.0)
    extraction_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return text, round(max(0.0, min(1.0, extraction_confidence)), 4)


def extract_page_records(path):
    if path.suffix.lower() != '.pdf':
        records = [
            {
                'page': index,
                'text': _sanitize_extracted_page_text(text),
                'text_origin': 'native',
                'extraction_confidence': _native_extraction_confidence(_sanitize_extracted_page_text(text)),
            }
            for index, text in enumerate(path.read_text(encoding='utf-8').split(PAGE_BREAK), 1)
        ]
        return _remove_repeated_page_noise(records)

    records = []
    pdf_reader = PdfReader(str(path))
    ocr_document = None
    try:
        for page_number, page in enumerate(pdf_reader.pages, 1):
            native_text = page.extract_text() or ''
            native_confidence = _native_extraction_confidence(native_text)
            needs_ocr = (
                config.OCR_ENABLED
                and (
                    len(native_text.strip()) < config.OCR_MIN_NATIVE_CHARS_PER_PAGE
                    or native_confidence < config.OCR_MIN_NATIVE_CONFIDENCE
                )
            )
            text = _sanitize_extracted_page_text(native_text)
            origin = 'native'
            confidence = _native_extraction_confidence(text)
            if needs_ocr:
                if ocr_document is None:
                    try:
                        import pymupdf
                        ocr_document = pymupdf.open(str(path))
                    except ImportError as exc:
                        raise RuntimeError('OCR necessário, mas PyMuPDF não está instalado.') from exc
                try:
                    ocr_text, ocr_confidence = _ocr_page(ocr_document, page_number)
                except Exception as exc:
                    if config.OCR_REQUIRED:
                        raise RuntimeError(
                            f'Falha no OCR da página {page_number} de {path.name}: {exc}'
                        ) from exc
                    ocr_text, ocr_confidence = '', 0.0
                if ocr_text.strip():
                    text = _sanitize_extracted_page_text(ocr_text)
                    origin = 'ocr'
                    confidence = _native_extraction_confidence(text) if not text.strip() else ocr_confidence
                elif config.OCR_REQUIRED:
                    raise RuntimeError(
                        f'OCR não produziu texto na página {page_number} de {path.name}.'
                    )
                else:
                    confidence = min(native_confidence, 0.35)
            records.append(
                {
                    'page': page_number,
                    'text': text,
                    'text_origin': origin,
                    'extraction_confidence': round(confidence, 4),
                }
            )
        return _remove_repeated_page_noise(records)
    finally:
        if ocr_document is not None:
            ocr_document.close()
    return records


def extract_pages(path):
    return [record['text'] for record in extract_page_records(path)]


def _starts(pages):
    out, offset = [], 0
    for text in pages:
        out.append(offset)
        offset += len(text) + 1
    return out


def _page(offset, starts):
    number = 1
    for index, start in enumerate(starts, 1):
        if start <= offset:
            number = index
        else:
            break
    return number


def _date_key(value, default):
    if value in (None, ''):
        return default
    try:
        return int(datetime.date.fromisoformat(str(value)).strftime('%Y%m%d'))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f'Data de vigência inválida no metadata: {value!r}') from exc


EFFECTIVE_RANGE_STATUSES = {'closed', 'open_start', 'open_end', 'unknown'}


def _effective_range_payload(metadata):
    """Materializa a vigência sem confundir limite aberto com dado desconhecido."""
    effective_from = metadata.get('effective_from')
    effective_to = metadata.get('effective_to')
    explicit_status = str(metadata.get('effective_range_status') or '').strip().casefold()

    if explicit_status:
        if explicit_status not in EFFECTIVE_RANGE_STATUSES:
            raise RuntimeError(
                f'Status de vigência inválido no metadata: {metadata.get("effective_range_status")!r}'
            )
        status = explicit_status
    elif effective_from and effective_to:
        status = 'closed'
    else:
        status = 'unknown'

    if status == 'closed' and (not effective_from or not effective_to):
        raise RuntimeError('Vigência fechada exige effective_from e effective_to.')
    if status == 'open_start' and (effective_from or not effective_to):
        raise RuntimeError('Vigência open_start exige effective_to e ausência de effective_from.')
    if status == 'open_end' and (not effective_from or effective_to):
        raise RuntimeError('Vigência open_end exige effective_from e ausência de effective_to.')

    payload = {'effective_range_status': status}
    if effective_from:
        payload['effective_from_day'] = _date_key(effective_from, 0)
    elif status == 'open_start':
        # Sentinela somente para limite deliberadamente aberto.
        payload['effective_from_day'] = 0

    if effective_to:
        payload['effective_to_day'] = _date_key(effective_to, 99991231)
    elif status == 'open_end':
        # Sentinela somente para limite deliberadamente aberto.
        payload['effective_to_day'] = 99991231

    return payload


def document_id_for(document, metadata=None):
    metadata = metadata or extract_metadata('', document)
    explicit = metadata.get('document_id')
    if explicit:
        return str(explicit)
    source_id = str(metadata.get('source_id') or 'local')
    return f'{source_id}::{document.stem}'


def build_chunks(document, pages, page_records=None, *, tokenizer=None):
    full = PAGE_BREAK.join(pages)
    meta = extract_metadata(full, document)
    doc_id = document_id_for(document, meta)
    starts = _starts(pages)
    quality_records = page_records or [
        {
            'page': index,
            'text': text,
            'text_origin': 'native',
            'extraction_confidence': _native_extraction_confidence(text),
        }
        for index, text in enumerate(pages, 1)
    ]
    prefix = embedding_metadata_prefix(meta)
    # The structural splitter budgets only its own text. The dense model also
    # receives the metadata prefix, the E5 passage prefix, and the hierarchy
    # label added below. Reserve those tokens before splitting so the configured
    # chunk size cannot exceed the embedding model's real input limit.
    if tokenizer is not None and hasattr(tokenizer, 'no_truncation'):
        tokenizer.no_truncation()

    def token_count(text):
        if tokenizer is None:
            return len(text)
        try:
            encoded = tokenizer.encode(text)
            return len(getattr(encoded, 'ids', encoded))
        except Exception:
            try:
                encoded = tokenizer.encode_batch([text])[0]
                return len(getattr(encoded, 'ids', encoded))
            except Exception as exc:
                raise RuntimeError('Could not safely count embedding-prefix tokens.') from exc

    embedding_overhead = token_count(config.DENSE_DOCUMENT_PREFIX + prefix)
    hierarchy_reserve = min(64, max(0, config.DENSE_MAX_TOKENS // 8))
    chunk_size = min(
        config.CHUNK_SIZE,
        config.DENSE_MAX_TOKENS - embedding_overhead - hierarchy_reserve,
    )
    if chunk_size <= 0:
        raise RuntimeError(
            'O prefixo de metadados excede o limite de tokens do embedding; '
            'reduza os metadados da fonte ou aumente RAG_DENSE_MAX_TOKENS.'
        )
    chunk_overlap = min(config.CHUNK_OVERLAP, chunk_size - 1)
    output = []
    chunk_source = build_structural_chunks(
        full,
        chunk_size,
        chunk_overlap,
        metadata=meta,
        tokenizer=tokenizer,
    )
    for chunk in chunk_source:
        if not chunk['text'].strip():
            continue
        start = chunk['start']
        # `end` é o fim do trecho NA FONTE; em chunks filhos `text` inclui o prefixo hierárquico e
        # len(text) superestimaria page_end perto de quebras de página.
        end = chunk.get('end', start + len(chunk['text']))
        page_start = _page(start, starts)
        page_end = _page(max(start, end - 1), starts)
        page_details = [
            {
                'page': int(record.get('page', index + 1)),
                'text_origin': str(record.get('text_origin') or 'native'),
                'extraction_confidence': round(float(record.get('extraction_confidence') or 0.0), 4),
            }
            for index, record in enumerate(quality_records[page_start - 1:page_end], page_start - 1)
        ]
        origins = {item['text_origin'] for item in page_details}
        if origins == {'native'}:
            text_origin = 'native'
        elif origins == {'ocr'}:
            text_origin = 'ocr'
        else:
            text_origin = 'mixed'
        extraction_confidence = (
            sum(item['extraction_confidence'] for item in page_details) / len(page_details)
            if page_details else 0.0
        )
        hierarchy = [str(item) for item in (chunk.get('hierarchy_path') or [])]
        body = chunk.get('page_content', chunk['text'])

        def compose_page_content(parts):
            label = ' > '.join(parts)
            content = prefix
            # Chunks filhos já carregam o caminho hierárquico no próprio texto; repeti-lo gasta tokens à toa.
            child_segment = chunk.get('segment_kind') in {'paragrafo', 'inciso', 'alinea', 'item'}
            if label and not body.startswith(label) and not child_segment:
                content += f' [HIERARQUIA: {label}]'
            return content + '\n' + body

        page_content = compose_page_content(hierarchy)
        # Títulos de capítulo/seção enriquecem a busca, mas o embedding trunca em silêncio acima de
        # DENSE_MAX_TOKENS: descarta primeiro o nível mais genérico (título da norma) até caber.
        while len(hierarchy) > 1 and token_count('passage: ' + page_content) > config.DENSE_MAX_TOKENS:
            hierarchy = hierarchy[1:]
            page_content = compose_page_content(hierarchy)
        embedding_text = config.DENSE_DOCUMENT_PREFIX + page_content
        if token_count(embedding_text) > config.DENSE_MAX_TOKENS:
            raise RuntimeError(
                'Chunk excede o limite de tokens do embedding; reduza o texto, a hierarquia ou '
                'RAG_DENSE_MAX_TOKENS para manter a invariante de tamanho.'
            )
        source_text = chunk.get('source_text', chunk.get('text'))
        retrieval_text = chunk.get('retrieval_text', page_content)
        output.append({
            **chunk,
            'text': chunk['text'],
            'source_text': source_text,
            'retrieval_text': retrieval_text,
            'page_content': page_content,
            'embedding_text': embedding_text,
            'source_start': chunk.get('source_start', chunk.get('start')),
            'source_end': chunk.get('source_end', chunk.get('end')),
            'doc_id': doc_id,
            'source': document.name,
            'source_id': meta.get('source_id') or document.stem,
            'page': page_start,
            'page_end': page_end,
            'text_origin': text_origin,
            'extraction_confidence': round(extraction_confidence, 4),
            'page_extraction': page_details,
            **meta,
            **_effective_range_payload(meta),
            'chunking_method': chunk.get('chunking_method') or 'structural',
        })
    return output


def embedding_kwargs():
    config.validate_gpu_runtime()
    return {'providers': list(config.FASTEMBED_PROVIDERS)}


def validate_model_cuda(model, *, label):
    """Valida se a sessão ONNX do embedding está efetivamente em CUDA."""
    onnx_model = getattr(model, 'model', None)
    session = getattr(onnx_model, 'model', None)
    if session is None:
        raise RuntimeError(f'{label}: sessão ONNX do FastEmbed não foi criada.')
    providers = session.get_providers()
    if 'CUDAExecutionProvider' not in providers:
        raise RuntimeError(
            f'{label}: CUDAExecutionProvider não está ativo na sessão ONNX. '
            f'Provedores ativos: {", ".join(providers) or "nenhum"}.'
        )


def ensure_collection(client):
    if not client.collection_exists(config.COLLECTION_NAME):
        vectors = {
            'dense': models.VectorParams(
                size=config.DENSE_DIM,
                distance=models.Distance.COSINE,
                on_disk=config.QDRANT_DENSE_ON_DISK,
            )
        }
        create_kwargs = {
            'collection_name': config.COLLECTION_NAME,
            'vectors_config': vectors,
            'sparse_vectors_config': {
                'sparse': models.SparseVectorParams(modifier=models.Modifier.IDF),
            },
        }
        if config.QDRANT_DENSE_QUANTIZATION == 'int8':
            create_kwargs['quantization_config'] = models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(
                    type=models.ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                )
            )
        client.create_collection(**create_kwargs)
    for field_name, field_type in config.QDRANT_PAYLOAD_INDEXES.items():
        try:
            field_schema = PAYLOAD_INDEX_TYPES[field_type]
        except KeyError as exc:
            raise RuntimeError(f'Tipo de índice de payload inválido para {field_name}: {field_type!r}.') from exc
        client.create_payload_index(
            collection_name=config.COLLECTION_NAME,
            field_name=field_name,
            field_schema=field_schema,
            wait=True,
        )


def _filter_for_doc_id(doc_id):
    return models.Filter(
        must=[models.FieldCondition(key='doc_id', match=models.MatchValue(value=doc_id))]
    )


def _point_ids_for_filter(client, filters):
    ids = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=config.COLLECTION_NAME,
            scroll_filter=filters,
            limit=256,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        for point in points:
            ids.update(
                value for value in (
                    getattr(point, 'id', None),
                    (point.payload or {}).get('source') if getattr(point, 'payload', None) else None,
                )
                if value is not None
            )
        if offset is None:
            break
    return ids


def source_point_ids(client, doc_id, legacy_source=None):
    ids = _point_ids_for_filter(client, _filter_for_doc_id(doc_id))
    if legacy_source and str(legacy_source) != str(doc_id):
        ids.update(
            _point_ids_for_filter(
                client,
                models.Filter(
                    must=[models.FieldCondition(
                        key='source',
                        match=models.MatchValue(value=str(legacy_source)),
                    )]
                ),
            )
        )
    return ids


def delete_point_ids(client, point_ids):
    point_ids = list(point_ids)
    if not point_ids:
        return
    for start in range(0, len(point_ids), config.QDRANT_UPSERT_BATCH_SIZE):
        batch = point_ids[start:start + config.QDRANT_UPSERT_BATCH_SIZE]
        client.delete(
            collection_name=config.COLLECTION_NAME,
            points_selector=models.PointIdsList(points=batch),
            wait=True,
        )


def upsert_points(client, points):
    points = list(points)
    batches = [
        points[start:start + config.QDRANT_UPSERT_BATCH_SIZE]
        for start in range(0, len(points), config.QDRANT_UPSERT_BATCH_SIZE)
    ]
    for index, batch in enumerate(batches):
        client.upsert(
            collection_name=config.COLLECTION_NAME,
            points=batch,
            wait=index == len(batches) - 1,
        )


def delete_doc(client, doc_id, legacy_source=None):
    delete_point_ids(client, source_point_ids(client, doc_id, legacy_source=legacy_source))


def replace_document_points(client, doc_id, new_points, legacy_source=None):
    if not new_points:
        raise ValueError(f'Nenhum chunk produzido para {doc_id}.')
    old_ids = set()
    filters = [_filter_for_doc_id(doc_id)]
    if legacy_source and str(legacy_source) != str(doc_id):
        filters.append(models.Filter(
            must=[models.FieldCondition(key='source', match=models.MatchValue(value=str(legacy_source)))]
        ))
    seen_ids = set()
    for point_filter in filters:
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=config.COLLECTION_NAME,
                scroll_filter=point_filter,
                limit=256,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            for point in points:
                if point.id not in seen_ids:
                    seen_ids.add(point.id)
                    old_ids.add(point.id)
            if offset is None:
                break
    new_ids = {point.id for point in new_points}
    try:
        # Nova versão primeiro: uma falha de upsert não destrói a versão antiga.
        upsert_points(client, new_points)
        delete_point_ids(client, old_ids - new_ids)
    except Exception as exc:
        try:
            delete_point_ids(client, new_ids - old_ids)
        except Exception as rollback_exc:
            raise RuntimeError(
                f'Falha na substituição de {doc_id}; limpeza parcial também falhou: {rollback_exc}'
            ) from exc
        raise RuntimeError(
            f'Falha na substituição de {doc_id}; versão anterior preservada quando possível.'
        ) from exc
    return old_ids


def _facet_payload_counts(client, field_name):
    response = client.facet(
        collection_name=config.COLLECTION_NAME,
        key=field_name,
        limit=100000,
        exact=True,
    )
    counts = {}
    for hit in getattr(response, 'hits', []) or []:
        value = getattr(hit, 'value', None)
        count = getattr(hit, 'count', None)
        if value is None and isinstance(hit, dict):
            value = hit.get('value')
            count = hit.get('count')
        if value is not None:
            counts[str(value)] = int(count or 0)
    return counts


def prune_stale_documents(client, active_names, *, delete=True, return_ids=False):
    if not config.RAG_PRUNE_STALE:
        return [] if return_ids else 0
    if not client.collection_exists(config.COLLECTION_NAME):
        return [] if return_ids else 0
    if hasattr(client, 'facet'):
        indexed_ids = set(_facet_payload_counts(client, 'doc_id'))
    else:
        indexed_ids = set()
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=config.COLLECTION_NAME,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                doc_id = payload.get('doc_id') or payload.get('source')
                if doc_id:
                    indexed_ids.add(str(doc_id))
            if offset is None:
                break
    stale = sorted(indexed_ids - {str(item) for item in active_names})
    if delete:
        for doc_id in stale:
            client.delete(
                collection_name=config.COLLECTION_NAME,
                points_selector=_filter_for_doc_id(doc_id),
                wait=True,
            )
    return stale if return_ids else len(stale)


def validate_dense_vectors(vectors, expected):
    for index, vector in enumerate(vectors):
        if len(vector) != config.DENSE_DIM:
            raise RuntimeError(
                f'embedding denso com dimensão inválida no chunk {index}: '
                f'{len(vector)} != {config.DENSE_DIM}'
            )
        norm_sq = 0.0
        for value in vector:
            numeric = float(value)
            if not math.isfinite(numeric):
                raise RuntimeError(f'embedding denso contém valor não finito no chunk {index}.')
            norm_sq += numeric * numeric
        if norm_sq <= 0.0:
            raise RuntimeError(f'embedding denso nulo no chunk {index}.')
    if len(vectors) != expected:
        raise RuntimeError(f'quantidade de embeddings densa inválida: {len(vectors)} != {expected}')


def main():
    parser = argparse.ArgumentParser(
        description='Sincroniza fontes e indexa o RAG jurídico.'
    )
    parser.add_argument(
        '--no-sync',
        action='store_true',
        help='não executa a coleta; indexa somente o conteúdo já presente no cache/fontes locais.',
    )
    parser.add_argument(
        '--only',
        action='append',
        dest='only_documents',
        default=[],
        metavar='ARQUIVO',
        help='reprocessa somente os arquivos informados; pode ser repetido. Os demais documentos permanecem no índice.',
    )
    args = parser.parse_args()

    config.ensure_directories()
    if not args.no_sync:
        sync_sources()
        sync_jurisprudencia()
    files = load_documents()
    if args.only_documents:
        requested = {Path(value).name for value in args.only_documents if str(value).strip()}
        available = {document.name for document in files}
        missing = sorted(requested - available)
        if missing:
            raise RuntimeError(
                'Arquivos informados em --only não encontrados no corpus local: '
                + ', '.join(missing)
            )
        target_files = [document for document in files if document.name in requested]
    else:
        target_files = files
    client = config.create_qdrant_client()
    manifest = read_manifest()
    if manifest is not None:
        from index_manifest import validate_manifest
        validate_manifest()
    elif client.collection_exists(config.COLLECTION_NAME) and client.count(config.COLLECTION_NAME, exact=True).count:
        if not args.only_documents:
            raise RuntimeError('Índice sem manifest. Remova db/qdrant e reindexe.')
        print('Aviso: índice existente sem manifest; recuperação direcionada ativada por --only.')

    ensure_collection(client)
    active_names = {document_id_for(document) for document in files}
    stale_removed = prune_stale_documents(client, active_names, delete=False, return_ids=True)
    deleted_manifest = []
    cache, errors, skipped = read_cache(), [], 0
    document_manifest = {}
    revocations = []
    fingerprint_base = _metadata_fingerprint_base()
    indexed_counts = _facet_payload_counts(client, 'doc_id') if client.collection_exists(config.COLLECTION_NAME) else {}
    cached_since_flush = 0

    print('Carregando modelos de embeddings/reranker na GPU.' if config.FASTEMBED_REQUIRE_CUDA else 'Carregando modelos de embeddings/reranker.')
    fastembed_kwargs = embedding_kwargs()
    dense = create_dense_embedding()
    if config.DENSE_BACKEND == 'fastembed' and config.FASTEMBED_REQUIRE_CUDA:
        validate_model_cuda(dense, label='Embedding denso')
    dense_tokenizer = getattr(getattr(dense, 'model', None), 'tokenizer', None)
    if config.DENSE_BACKEND == 'fastembed' and dense_tokenizer is None:
        raise RuntimeError('Tokenizer do embedding denso indisponível; o chunking não pode medir o limite de tokens com segurança.')
    sparse = SparseTextEmbedding(model_name=config.SPARSE_MODEL, **fastembed_kwargs)

    for document in target_files:
        digest = file_hash(document)
        metadata_digest = metadata_fingerprint(document, base=fingerprint_base)
        document_meta = extract_metadata('', document)
        doc_id = document_id_for(document, document_meta)
        count_filter = _filter_for_doc_id(doc_id)
        entry = cache.get(document.name)
        indexed_count = int(indexed_counts.get(doc_id, 0))

        if cache_entry_is_valid(
            entry,
            digest,
            metadata_digest,
            indexed_count,
        ):
            skipped += 1

            document_manifest[doc_id] = {
                'sha256': digest,
                'chunks': indexed_count,
                'source': document.name,
                'source_id': document_meta.get('source_id'),
                'regime_juridico': document_meta.get('regime_juridico'),
                'status': document_meta.get('status'),
                'metadata_fingerprint': metadata_digest,
            }
            if document_meta.get('revogado') or document_meta.get('status') == 'revogado':
                revocations.append({'doc_id': doc_id, 'source': document.name, 'status': document_meta.get('status'), 'effective_to': document_meta.get('effective_to')})
            continue
        try:
            page_records = extract_page_records(document)
            pages = [record['text'] for record in page_records]
            chunks = build_chunks(
                document,
                pages,
                page_records=page_records,
                tokenizer=dense_tokenizer,
            )
            if not chunks:
                print('Aviso: sem texto em', document.name)
                errors.append(document.name)
                continue
            embedding_inputs = [item['embedding_text'] for item in chunks]
            validate_embedding_inputs(dense, embedding_inputs, label=document.name)
            dense_vectors = list(dense.embed(embedding_inputs))
            validate_dense_vectors(dense_vectors, len(chunks))
            sparse_vectors = list(sparse.embed([item['page_content'] for item in chunks]))
            if len(sparse_vectors) != len(chunks):
                raise RuntimeError(
                    f'quantidade de embeddings esparsas inválida: {len(sparse_vectors)} != {len(chunks)}'
                )
            points = []
            for index, item in enumerate(chunks):
                point_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{doc_id}|{item['unit_id']}|{item['chunk_index']}|{item['page_content']}",
                    )
                )
                payload = dict(item)
                for redundant_key in ('text', 'source_text', 'retrieval_text', 'embedding_text', 'full_unit_text'):
                    payload.pop(redundant_key, None)
                points.append(
                    models.PointStruct(
                        id=point_id,
                        vector={
                            'dense': dense_vectors[index].tolist(),
                            'sparse': models.SparseVector(
                                indices=sparse_vectors[index].indices.tolist(),
                                values=sparse_vectors[index].values.tolist(),
                            ),
                        },
                        payload=payload,
                    )
                )
            replace_document_points(client, doc_id, points, legacy_source=document.name)
            cache[document.name] = {'sha256': digest, 'metadata_fingerprint': metadata_digest, 'chunks': len(points), 'doc_id': doc_id, 'source_id': document_meta.get('source_id')}
            indexed_counts[doc_id] = len(points)
            cached_since_flush += 1
            document_manifest[doc_id] = {
                'sha256': digest,
                'chunks': len(points),
                'source': document.name,
                'source_id': document_meta.get('source_id'),
                'regime_juridico': document_meta.get('regime_juridico'),
                'status': document_meta.get('status'),
                'metadata_fingerprint': metadata_digest,
            }
            if document_meta.get('revogado') or document_meta.get('status') == 'revogado':
                revocations.append({'doc_id': doc_id, 'source': document.name, 'status': document_meta.get('status'), 'effective_to': document_meta.get('effective_to')})
            if cached_since_flush >= 50:
                write_cache(cache)
                cached_since_flush = 0
            print(f'Indexado: {document.name} ({len(points)} chunks)')
        except Exception as exc:
            print(f'ERRO ao indexar {document.name}: {exc}. A versão anterior permanece disponível quando o upsert falhar.')
            errors.append(document.name)

    write_cache(cache)
    total = client.count(config.COLLECTION_NAME, exact=True).count
    print('Total:', total, '| pulados (sem alteração):', skipped, '| fontes obsoletas removidas:', stale_removed)
    if errors:
        print('Arquivos com erro (não indexados):', ', '.join(errors))
        print('Manifesto não atualizado porque a indexação terminou parcialmente; execute novamente após corrigir as fontes.')
        return 1
    for name, entry in cache.items():
        if isinstance(entry, dict) and entry.get('doc_id') and name in {document.name for document in files}:
            document_manifest.setdefault(str(entry['doc_id']), {**entry, 'source': name})
    for doc_id in stale_removed:
        delete_doc(client, doc_id)
        deleted_manifest.append({
            'doc_id': doc_id,
            'reason': 'stale',
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
    write_manifest(
        documents=document_manifest,
        deletions=deleted_manifest,
        revocations=revocations,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
