"""
Chunking estrutural para leis, súmulas e outros documentos jurídicos.

O RecursiveCharacterTextSplitter original corta por contagem de caracteres,
sem noção de onde um artigo ou uma súmula começa/termina. Isso quebra:
1. um artigo no meio (o chunk N termina em "...aplicando-se, no que couber,
   o disposto no" e o chunk N+1 começa com "art. 42");
2. a costura entre páginas: como o ingest original fatiava por página antes
   de rodar o splitter, um artigo que atravessa a quebra de página nunca
   era visto como texto contínuo -- ele já chegava cortado no splitter.

Este módulo resolve os dois problemas:
- opera sobre o texto do documento inteiro (não por página), então nada se
  perde na quebra de página;
- primeiro tenta reconhecer a unidade jurídica nativa (artigo de lei ou
  súmula/enunciado) via regex e usa essa unidade como fronteira de chunk,
  em vez de um tamanho fixo de caracteres;
- se uma unidade for grande demais para o modelo de embedding (ex.: um
  artigo com uma tabela/anexo longo embutido), ela é subdividida só para
  fins de geração do vetor de busca -- mas o texto COMPLETO da unidade
  (`full_unit_text`) é preservado no payload e é o que efetivamente vai
  para o contexto do LLM. Ou seja: a busca semântica pode "ancorar" em um
  parágrafo específico, mas a resposta final sempre recebe o artigo ou a
  súmula inteiros, nunca picados.
"""
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

# "Art. 37", "Artigo 5º", "Art. 42-A." — no início de uma linha.
ARTIGO_RE = re.compile(
    r"(?m)^\s*(Art(?:igo)?\.?\s*\d+[ºo°]?-?[A-Z]?\.?)\s"
)

# "Súmula nº 281", "Súmula 281", "Enunciado nº 12" — no início de uma linha.
SUMULA_RE = re.compile(
    r"(?m)^\s*(S[uú]mula\s*n?[ºo°.]*\s*\d+|Enunciado\s*n?[ºo°.]*\s*\d+)\b",
    re.IGNORECASE,
)

# Marcadores nesta ordem de prioridade: um documento pode ter ambos (ex.: um
# boletim de jurisprudência às vezes cita artigos de lei dentro do texto de
# uma súmula), então tentamos "artigo" primeiro só quando ele domina o
# documento; senão caímos para súmula.
_MARKERS = ((ARTIGO_RE, "artigo"), (SUMULA_RE, "sumula"))


def _find_units(text: str, marker_re: re.Pattern, kind: str):
    matches = list(marker_re.finditer(text))
    if len(matches) < 2:
        # Menos de duas ocorrências não é estrutura suficiente pra confiar
        # nessa segmentação (pode ser uma citação avulsa, não o documento
        # inteiro organizado em artigos/súmulas).
        return None

    units = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()]
        if preamble.strip():
            units.append({
                "kind": "generic", "ref": None,
                "start": 0, "text": preamble.strip(),
            })

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk_text = text[start:end].strip()
        if chunk_text:
            units.append({
                "kind": kind, "ref": m.group(1).strip(),
                "start": start, "text": chunk_text,
            })
    return units


def _detect_units(full_text: str):
    for marker_re, kind in _MARKERS:
        units = _find_units(full_text, marker_re, kind)
        if units:
            return units
    # Documento sem estrutura de artigo/súmula reconhecível (ex.: edital
    # comum) -- trata como uma unidade genérica só, que o passo seguinte
    # vai subdividir por tamanho normalmente.
    return [{"kind": "generic", "ref": None, "start": 0, "text": full_text}]


def build_structural_chunks(full_text: str, max_size: int, overlap: int):
    """Retorna uma lista de dicts prontos para virar chunks indexáveis.

    Cada dict tem:
      - text: pedaço usado para gerar o embedding (pode ser a unidade
        inteira, ou um fragmento dela se ela for grande demais)
      - full_unit_text: texto completo do artigo/súmula, sempre
      - unit_kind: "artigo" | "sumula" | "generic"
      - unit_ref: "Art. 37", "Súmula nº 281", ou None
      - start: offset do início da unidade no texto completo do documento
        (usado depois para localizar a página)
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    for unit in _detect_units(full_text):
        full_unit_text = unit["text"]

        if len(full_unit_text) <= max_size:
            chunks.append({
                "text": full_unit_text,
                "full_unit_text": full_unit_text,
                "unit_kind": unit["kind"],
                "unit_ref": unit["ref"],
                "start": unit["start"],
            })
            continue

        # Unidade grande demais para um único vetor de embedding de boa
        # qualidade (ex.: artigo com uma tabela/anexo longo). Subdividimos
        # só para a busca; full_unit_text continua completo em cada pedaço,
        # então não importa qual fragmento a busca semântica encontrar --
        # o contexto enviado ao LLM sempre traz a unidade inteira.
        for piece in splitter.split_text(full_unit_text):
            chunks.append({
                "text": piece,
                "full_unit_text": full_unit_text,
                "unit_kind": unit["kind"],
                "unit_ref": unit["ref"],
                "start": unit["start"],
            })

    return chunks