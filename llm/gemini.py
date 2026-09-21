from __future__ import annotations
import os

class GeminiLLM:
    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("RAG_GEMINI_MODEL","gemini-2.5-flash")
        self.api_key = os.getenv("GOOGLE_API_KEY","")

    def chat(self, question: str, context: str) -> str:
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Instale google-genai para usar o provider Gemini.") from exc
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY não configurada.")
        client = genai.Client(api_key=self.api_key)
        prompt = (
            "Você é um assistente jurídico especializado em Direito Público brasileiro.\n"
            "Responda somente com base no contexto e preserve as citações [F#].\n\n"
            f"CONTEXTO:\n{context}\n\nPERGUNTA:\n{question}"
        )
        response = client.models.generate_content(model=self.model, contents=prompt)
        return (getattr(response, "text", None) or "").strip()
