from __future__ import annotations
from typing import Any
from openai import OpenAI
from config import SETTINGS

SYSTEM_PROMPT = """Você é um assistente jurídico especializado em Direito Público brasileiro.
Responda somente com base nas fontes fornecidas no contexto.
Não invente artigos, precedentes, números de processo ou links.
Indique a jurisdição e a esfera quando houver risco de confusão.
Hierarquia: Constituição/lei/decreto/ato normativo > jurisprudência/controle > orientação oficial > doutrina.
Quando a evidência for insuficiente, diga expressamente que não foi localizada evidência suficiente.
Use as citações [F#] exatamente como aparecem no contexto."""
 
class OpenAICompatibleLLM:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
        self.client = OpenAI(base_url=base_url or SETTINGS.llm_base_url,
                             api_key=api_key or SETTINGS.llm_api_key or "local")
        self.model = model or SETTINGS.llm_model

    def chat(self, question: str, context: str, temperature: float = 0.0) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"CONTEXTO\n{context}\n\nPERGUNTA\n{question}"},
            ],
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip()
