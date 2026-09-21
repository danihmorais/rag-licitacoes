from __future__ import annotations
import os
import httpx

class OllamaLLM:
    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL","http://127.0.0.1:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL","gemma3")

    def chat(self, question: str, context: str) -> str:
        prompt = (
            "Você é um assistente jurídico especializado em Direito Público brasileiro. "
            "Use somente o contexto fornecido e preserve as citações [F#].\n\n"
            f"CONTEXTO:\n{context}\n\nPERGUNTA:\n{question}"
        )
        r = httpx.post(
            f"{self.base_url}/api/generate",
            json={"model":self.model,"prompt":prompt,"stream":False},
            timeout=120,
        )
        r.raise_for_status()
        return str(r.json().get("response","")).strip()
