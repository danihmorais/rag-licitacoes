# Plano de ação — Correções do `rag-licitacoes`

Sequência única de correções, executadas uma por vez. A recomendação é concluir e validar cada item antes de avançar para o próximo.

## 1. Corrigir a invalidação indevida do cache

### Problema
Cada sincronização pode invalidar o cache de todos os documentos mesmo quando o conteúdo não mudou. O `metadata_fingerprint` considera os bytes do sidecar `.json`, enquanto `retrieved_at` é atualizado a cada sincronização. Além disso, `LLM_PROVIDER` e `LLM_MODEL` entram no fingerprint, embora o modelo de geração não seja utilizado na ingestão.

### Arquivos principais
- `ingest.py`
- `scripts/sync_sources.py`
- `jurisprudencia/collector.py`

### Correção
- Remover `retrieved_at` da composição do fingerprint; ou impedir a regravação do sidecar quando o `sha256` do conteúdo não mudou.
- Remover `LLM_PROVIDER` e `LLM_MODEL` do fingerprint.
- Preservar a validade do cache quando apenas o modelo de geração do LLM for alterado.
- Garantir que a sincronização não regrave metadados sem mudança real de conteúdo.

### Critério de validação
Executar duas sincronizações consecutivas sem alteração das fontes e confirmar que:
- o mesmo documento permanece com cache válido;
- não ocorre novo chunking/embedding para documentos inalterados;
- trocar `RAG_LLM_MODEL` não invalida o cache.

### Referência do relatório
Seções 1.1 e 1.2.

---

## 2. Eliminar a tokenização quadrática no chunking

### Problema
Em `build_structural_chunks`, `unit["text"]` é tokenizado repetidamente dentro do loop de chunks por meio de `_token_count(unit["text"])`.

Em documentos grandes, a mesma unidade inteira é tokenizada uma vez por chunk, produzindo custo quadrático.

### Arquivo principal
- `chunking.py`

### Correção
- Calcular a informação necessária sobre `full_unit_text` uma única vez por unidade.
- Fazer esse cálculo antes do loop que percorre os chunks.
- Reutilizar o resultado dentro do loop.

### Critério de validação
Confirmar que a tokenização do texto completo não é repetida para cada chunk.

Para o caso de aproximadamente 800 mil caracteres, o comportamento esperado é deixar de tokenizar centenas de vezes o tamanho do documento. O relatório mediu redução de aproximadamente `379×` para algo próximo de `4×` do texto processado nessa etapa.

### Referência do relatório
Seção 1.3.

---

## 3. Parar de regravar o cache inteiro a cada documento

### Problema
`write_cache(cache)` é executado dentro do loop principal da ingestão e reescreve o JSON inteiro, com `indent=2` e `fsync`, depois de cada documento.

Isso faz o custo crescer quadraticamente com o número de documentos.

### Arquivo principal
- `ingest.py`

### Correção
- Retirar a gravação completa do cache de dentro do processamento de cada documento.
- Gravar o cache periodicamente, por exemplo, a cada 50 documentos.
- Gravar obrigatoriamente ao final da execução.
- Manter a escrita atômica.

### Critério de validação
Verificar que:
- o cache não é regravado uma vez por documento;
- uma ingestão de milhares de documentos produz poucas gravações;
- o cache continua consistente mesmo em caso de interrupção entre gravações.

### Referência do relatório
Seção 1.4.

---

## 4. Limitar a geração do LLM e ajustar o Ollama

### Problema
Os provedores de LLM não usam streaming e `RAG_LLM_MAX_TOKENS=0` permite geração sem limite próprio. No Ollama, o contexto mínimo configurado é maior que o necessário para o contexto efetivamente recuperado.

Além disso, quando o Evidence Gate rejeita uma resposta, `answer_query` pode fazer uma segunda geração completa.

### Arquivos principais
- `config.py`
- `llm/openai_compatible.py`
- `llm/ollama.py`
- `query.py`

### Correção
- Definir um valor padrão adequado para `RAG_LLM_MAX_TOKENS`.
- Enviar esse limite aos provedores compatíveis.
- Configurar `keep_alive` no Ollama para evitar descarregamento desnecessário do modelo.
- Ajustar `RAG_OLLAMA_NUM_CTX` para um valor compatível com o contexto realmente utilizado.
- Avaliar o fluxo do Evidence Gate para reduzir gerações completas duplicadas quando isso puder ser feito sem perda de qualidade.

### Critério de validação
Medir:
- tempo total da consulta;
- quantidade de tokens gerados;
- uso de VRAM;
- comportamento após período de ociosidade do Ollama;
- frequência de segunda geração após rejeição do Evidence Gate.

### Referência do relatório
Seção 2.1 e item 2.5.

---

## 5. Corrigir a portabilidade da ingestão e evitar reindexações acidentais

### Problema
A ingestão força CUDA no FastEmbed e não respeita `RAG_FASTEMBED_REQUIRE_CUDA`. Além disso, qualquer alteração em `chunking.py`, inclusive comentário, pode invalidar a coleção porque o manifesto usa o SHA-256 do arquivo.

O CI também instala dependências CUDA em runners sem GPU, e há um arquivo de DLQ de teste versionado em `db/`.

### Arquivos principais
- `ingest.py`
- `index_manifest.py`
- arquivos de CI (`ci.yml`, `legal-ingestion.yml`)
- testes de jurisprudência
- `.gitignore`

### Correção
- Usar `embedding_kwargs()` na ingestão.
- Validar CUDA somente quando `RAG_FASTEMBED_REQUIRE_CUDA` estiver habilitado.
- Criar uma constante de versão, por exemplo `CHUNKING_VERSION`.
- Usar a versão do algoritmo no manifesto em vez do hash integral de `chunking.py`.
- Alterar `CHUNKING_VERSION` somente quando a lógica de chunking mudar.
- Criar `requirements-ci.txt` com dependências adequadas para CPU.
- Remover o artefato `db/jurisprudencia_dlq.jsonl` do versionamento.
- Alterar o teste para usar `tmp_path / "dlq.jsonl"`.

### Critério de validação
Confirmar que:
- `RAG_FASTEMBED_REQUIRE_CUDA=0` permite ingestão sem GPU;
- uma edição apenas de comentário em `chunking.py` não exige reindexação;
- o CI não instala a pilha CUDA completa;
- testes não escrevem artefatos no `db/` do projeto.

### Referência do relatório
Seções 4.2, 4.3, 4.5 e 4.6.

---

## 6. Corrigir o BM25 para usar IDF

### Problema
A coleção utiliza `SparseVectorParams()` sem `modifier=IDF`, e a consulta esparsa usa `sparse.embed([query])`.

Isso reduz a vantagem do BM25 porque termos frequentes recebem peso semelhante a termos raros.

### Arquivos principais
- `ingest.py`
- `query.py`

### Correção
- Criar o vetor esparso com `models.Modifier.IDF`.
- Utilizar `query_embed` na consulta.
- Manter a lógica compatível com o modelo sparse atualmente utilizado.

### Critério de validação
- Recriar a coleção.
- Reindexar o corpus.
- Rodar `evaluation.py` antes e depois da alteração.
- Comparar principalmente recall, precisão e qualidade dos resultados híbridos.

### Dependência
Esta alteração exige recriação da coleção e reindexação do corpus.

### Referência do relatório
Seção 4.1.

---

## 7. Otimizar a recuperação de contexto no Qdrant

### Problema
`expand_context` lê uma unidade inteira do Qdrant para cada resultado e filtra os vizinhos em Python. Em documentos `generic`, uma unidade pode conter o documento inteiro.

A consulta também executa buscas auxiliares sequenciais para a Lei 14.133/2021 e o Manual do TCU em praticamente toda consulta com resultado.

### Arquivos principais
- `query.py`
- `chunking.py`
- configuração/manifesto de índices do Qdrant, conforme necessário

### Correção
- Garantir `chunk_index` como inteiro.
- Indexar `chunk_index` no Qdrant.
- Filtrar no servidor o intervalo `idx-N` até `idx+N`.
- Solicitar somente os campos de payload necessários.
- Evitar carregar o documento inteiro para obter vizinhos.
- Trocar as duas buscas-base por `query_batch_points` ou execução paralela.
- Avaliar inclusão do contexto auxiliar somente quando o reranker atingir nota mínima.
- Avaliar redução de `RAG_CANDIDATES_K` de 60 para aproximadamente 30–40.

### Critério de validação
Medir:
- tempo de recuperação;
- quantidade de bytes transferidos;
- quantidade de pontos lidos;
- tempo do reranker;
- qualidade dos resultados no `evaluation.py`.

### Dependência
Mudanças de índices/manifesto que afetem a compatibilidade da coleção podem exigir reindexação.

### Referência do relatório
Seções 2.2, 2.3 e 2.4.

---

## 8. Reduzir operações desnecessárias durante a ingestão

### Problema
A ingestão faz leituras, contagens e inicializações repetidas no Qdrant, além de transferir dados que não são necessários.

### Arquivo principal
- `ingest.py`

### Correção
- Em `prune_stale_documents`, usar `facet("doc_id")` em vez de varrer a coleção com payload completo.
- Evitar `with_vectors=True` em `replace_document_points` quando não for necessário.
- Gravar a nova versão primeiro e remover depois somente os pontos antigos que não reapareceram.
- Eliminar `client.count(exact=True)` por documento quando o resultado não for usado para decidir o processamento.
- Executar `ensure_collection` uma única vez.
- Remover inicializações duplicadas das mesmas variáveis.
- Calcular o fingerprint de `metadata.py` e `chunking.py` uma única vez por execução.
- Evitar chamar `extract_metadata()` duas vezes para o mesmo documento.

### Critério de validação
Confirmar redução do número de chamadas ao Qdrant, do volume de payload transferido e do tempo gasto por documento.

### Referência do relatório
Seção 1.6.

---

## 9. Enxugar o payload e avaliar quantização dos embeddings

### Problema
Cada ponto armazena várias cópias ou representações sobrepostas do texto, como `text`, `source_text`, `retrieval_text`, `page_content`, `embedding_text` e `full_unit_text`, além de metadados repetidos.

A coleção também utiliza a configuração padrão do Qdrant, sem avaliação de quantização e armazenamento otimizado.

### Arquivo principal
- `ingest.py`

### Correção
- Mapear quais campos são realmente consumidos por ingestão, consulta, reranking e geração.
- Reduzir duplicações no payload.
- Manter o texto necessário em uma representação principal, por exemplo `page_content`, e utilizar offsets/metadados para reconstrução do contexto quando possível.
- Avaliar quantização escalar `int8` do vetor denso.
- Avaliar `on_disk` e ajustes de armazenamento/HNSW compatíveis com o corpus.

### Critério de validação
Comparar:
- tamanho da coleção;
- uso de RAM/VRAM;
- tempo de busca;
- tempo de transferência;
- qualidade dos resultados antes e depois.

### Dependência
A alteração do schema/payload da coleção e a mudança de configuração dos vetores podem exigir recriação da coleção e reindexação.

### Referência do relatório
Seção 4.4.

---

## 10. Otimizar embeddings, upserts e coleta de fontes/jurisprudência

### Problema
A ingestão processa poucos chunks por documento, faz embedding e gravação documento a documento, enquanto a coleta de fontes e jurisprudência é amplamente sequencial.

Na jurisprudência, o STF pode abrir um Chromium novo para cada variante da busca. O boletim do TCU pode ser baixado e processado repetidamente dentro da mesma execução. A sincronização web também não usa requisições condicionais.

### Arquivos principais
- `ingest.py`
- `jurisprudencia/collector.py`
- `jurisprudencia/batch.py`
- `scripts/sync_sources.py`
- `scripts/web_sources.py`

### Correção
#### Embeddings e Qdrant
- Acumular chunks de vários documentos.
- Embutir lotes de aproximadamente 256 chunks.
- Aumentar o tamanho dos lotes de upsert em relação ao valor atual.
- Usar `wait=True` somente quando necessário, preferencialmente no último envio da sequência.

#### STF
- Abrir um único Chromium por execução do lote.
- Reutilizar o contexto do navegador.
- Reutilizar o token WAF entre consultas.

#### Boletim do TCU
- Fazer cache em memória por processo; ou
- implementar cache em disco com `If-Modified-Since`.

#### Sincronização das fontes
- Usar um pool pequeno de threads por host, respeitando os limites dos sites.
- Implementar cache condicional por URL.
- Usar `ETag` e/ou `If-Modified-Since` quando suportado.
- Baixar e extrair novamente somente quando o conteúdo realmente mudar.

#### URLs com falha
- Definir orçamento total de tempo por URL.
- Registrar falhas recentes.
- Evitar insistir imediatamente em URLs que falharam na execução anterior.

#### Detalhes de jurisprudência
- Avaliar paralelização controlada quando `RAG_JURISPRUDENCIA_DETAIL` ou `RAG_JURISPRUDENCIA_WITH_CONTENT` estiver habilitado.

### Critério de validação
Comparar:
- tempo total de ingestão;
- uso da GPU durante embeddings;
- número de requisições HTTP;
- número de inicializações do Chromium;
- quantidade de downloads repetidos;
- tempo total de coleta de jurisprudência;
- quantidade de upserts e chamadas ao Qdrant.

### Referência do relatório
Seções 1.5, 3.1, 3.2, 3.3, 3.4 e 3.5.

---

# Ordem de execução

1. Corrigir a invalidação indevida do cache
2. Eliminar a tokenização quadrática no chunking
3. Parar de regravar o cache inteiro a cada documento
4. Limitar a geração do LLM e ajustar o Ollama
5. Corrigir a portabilidade da ingestão e evitar reindexações acidentais
6. Corrigir o BM25 para usar IDF
7. Otimizar a recuperação de contexto no Qdrant
8. Reduzir operações desnecessárias durante a ingestão
9. Enxugar o payload e avaliar quantização dos embeddings
10. Otimizar embeddings, upserts e coleta de fontes/jurisprudência

# Regra de execução

Cada número deve ser tratado como uma alteração independente:

**implementar → executar testes → validar resultado → só então avançar para o próximo número.**

Os itens **6** e **9** devem ser planejados para a mesma recriação/reindexação da coleção, quando possível, para evitar duas reindexações completas.
