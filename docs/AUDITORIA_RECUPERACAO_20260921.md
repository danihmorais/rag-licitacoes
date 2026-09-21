# Auditoria de recuperação — 21/09/2026

O repositório remoto perdeu o histórico. O material preservado nas conversas registrou a arquitetura como RAG híbrido **dense + BM25 + RRF + reranker**, com chunking jurídico estrutural, metadados de autoridade/vigência e coleta estruturada de jurisprudência para TCU, TCESP, STJ e STF.

Arquivos anteriormente auditados: README.md, config.py, chunking.py, metadata.py, ingest.py, query.py, index_manifest.py, jurisprudencia/{collector.py,schema.py}, scripts/{sources.py,sources_additional.py,sync_sources.py}, llm/{factory.py,openai_compatible.py}, testes e documentação.

Pontos preservados na reconstrução:
- score de evidência aplicado item a item;
- autoridade por tribunal;
- tribunal obrigatório em fontes jurisprudenciais;
- sidecar como fonte explícita de metadados;
- IDs estruturais com posição para evitar colisão;
- manifesto com hash da lógica de chunking;
- cache de ingestão persistido incrementalmente;
- contexto truncado respeitando a ordem de relevância.

A reconstrução é funcional, mas não pode ser considerada cópia byte a byte dos arquivos perdidos. O corpus PDF, embeddings, cache do Qdrant e outros artefatos binários precisam ser gerados novamente.
