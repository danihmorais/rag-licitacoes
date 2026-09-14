from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from typing import Any


@dataclass(slots=True)
class JurisprudenciaRecord:
    tribunal: str
    numero_processo: str
    orgao_julgador: str | None = None
    relator: str | None = None
    data: str | None = None
    data_publicacao: str | None = None
    assunto: list[str] = field(default_factory=list)
    ementa: str | None = None
    tese: str | None = None
    decisao: str | None = None
    inteiro_teor: str | None = None
    url_oficial: str | None = None
    tipo_decisao: str | None = None
    numero_decisao: str | None = None
    origem: str | None = None
    data_autuacao: str | None = None
    partes: list[str] = field(default_factory=list)
    situacao: str | None = None
    retrieved_at: str | None = None
    sha256: str | None = None
    version_sha256: str | None = None

    def validate(self) -> None:
        errors = []
        tribunal = str(self.tribunal or '').strip().upper()
        process = str(self.numero_processo or '').strip()
        if tribunal not in {'TCU', 'TCESP', 'STJ', 'STF'}:
            errors.append(f'tribunal inválido: {self.tribunal!r}')
        if not process:
            errors.append('numero_processo é obrigatório')
        if self.assunto is not None and not isinstance(self.assunto, list):
            errors.append('assunto deve ser lista')
        if self.partes is not None and not isinstance(self.partes, list):
            errors.append('partes deve ser lista')
        if self.url_oficial and not re.match(r'^https?://', str(self.url_oficial), re.I):
            errors.append('url_oficial deve ser HTTP(S)')
        if errors:
            raise ValueError('Registro de jurisprudência inválido: ' + '; '.join(errors))

    @property
    def document_key(self) -> str:
        self.validate()
        parts = [self.tribunal or '', self.numero_processo or '', self.numero_decisao or '', self.tipo_decisao or '']
        if not self.numero_decisao:
            parts.append(re.sub(r'\s+', ' ', self.ementa or '').strip()[:800])
        if not self.numero_processo:
            parts.append(self.url_oficial or '')
        base = '|'.join(parts)
        return hashlib.sha256(base.encode('utf-8')).hexdigest()[:20]

    def canonical_payload(self) -> dict[str, Any]:
        self.validate()
        payload = self.to_dict()
        payload.pop('retrieved_at', None)
        payload.pop('sha256', None)
        payload.pop('version_sha256', None)
        if payload.get('url_oficial'):
            payload['url_oficial'] = re.sub(r';jsessionid=[^?/#]+', '', str(payload['url_oficial']), flags=re.I)
        return payload

    def calculate_version_sha256(self) -> str:
        raw = json.dumps(self.canonical_payload(), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        return hashlib.sha256(raw).hexdigest()

    def to_index_text(self) -> str:
        self.validate()
        lines = [f'TRIBUNAL: {self.tribunal}', f'PROCESSO: {self.numero_processo}']
        if self.numero_decisao:
            lines.append(f'DECISÃO/ACÓRDÃO: {self.numero_decisao}')
        if self.tipo_decisao:
            lines.append(f'TIPO: {self.tipo_decisao}')
        if self.orgao_julgador:
            lines.append(f'ÓRGÃO JULGADOR/COLEGIADO: {self.orgao_julgador}')
        if self.relator:
            lines.append(f'RELATOR: {self.relator}')
        if self.data:
            lines.append(f'DATA DO JULGAMENTO/SESSÃO: {self.data}')
        if self.data_publicacao:
            lines.append(f'DATA DA PUBLICAÇÃO: {self.data_publicacao}')
        if self.data_autuacao:
            lines.append(f'DATA DA AUTUAÇÃO: {self.data_autuacao}')
        if self.situacao:
            lines.append(f'SITUAÇÃO: {self.situacao}')
        if self.assunto:
            lines.append('ASSUNTOS: ' + '; '.join(self.assunto))
        if self.partes:
            lines.append('PARTES: ' + ' | '.join(self.partes))
        if self.ementa:
            lines.extend(['', 'EMENTA:', self.ementa])
        if self.tese:
            lines.extend(['', 'TESE/ENTENDIMENTO:', self.tese])
        if self.decisao:
            lines.extend(['', 'DECISÃO:', self.decisao])
        if self.inteiro_teor:
            lines.extend(['', 'INTEIRO TEOR:', self.inteiro_teor])
        if self.url_oficial:
            lines.extend(['', f'FONTE OFICIAL: {self.url_oficial}'])
        return '\n'.join(lines).strip() + '\n'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
