from __future__ import annotations

import json
import asyncio

import httpx

from app.config import Settings


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.ollama_base_url.rstrip("/")
        self._timeout = float(settings.request_timeout_sec)

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        # trust_env=False - иначе системный proxy ломает localhost Ollama (503)
        return httpx.AsyncClient(timeout=timeout or self._timeout, trust_env=False)

    async def list_models(self) -> list[str]:
        # 0. Запрос списка моделей
        async with self._client() as client:
            response = await client.get(f"{self._base}/api/tags")
            response.raise_for_status()
            payload = response.json()

        # 1. Нормализация имён
        return [item.get("name", "") for item in payload.get("models", []) if item.get("name")]

    async def embed(self, texts: list[str], batch_size: int = 16) -> list[list[float]]:
        # 0. Подготовка
        if not texts:
            return []

        vectors: list[list[float]] = []

        # 1. Батчами через /api/embed (быстрее на большом корпусе)
        async with self._client(timeout=max(self._timeout, 180.0)) as client:
            for start in range(0, len(texts), batch_size):
                chunk = texts[start : start + batch_size]
                print(f"[embed] {start + 1}-{start + len(chunk)} / {len(texts)}")
                batch_vectors = await self._embed_batch(client, chunk)
                vectors.extend(batch_vectors)

        # 2. Результат
        return vectors

    async def _embed_batch(
        self,
        client: httpx.AsyncClient,
        texts: list[str],
    ) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await client.post(
                    f"{self._base}/api/embed",
                    json={
                        "model": self._settings.ollama_embed_model,
                        "input": texts,
                        "keep_alive": self._settings.ollama_keep_alive,
                    },
                )
                if response.status_code in {404, 405}:
                    # Старый endpoint только по одному
                    out: list[list[float]] = []
                    for text in texts:
                        legacy = await client.post(
                            f"{self._base}/api/embeddings",
                            json={
                                "model": self._settings.ollama_embed_model,
                                "prompt": text,
                            },
                        )
                        legacy.raise_for_status()
                        out.append(legacy.json()["embedding"])
                    return out
                if response.status_code == 503:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                data = response.json()
                if "embeddings" in data and data["embeddings"]:
                    return data["embeddings"]
                if "embedding" in data:
                    return [data["embedding"]]
                raise RuntimeError(f"Unexpected embed response keys: {list(data)}")
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                await asyncio.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Ollama embed failed: {last_error}")

    async def chat(self, system: str, user: str, max_tokens: int = 768, schema: dict | None = None, reasoning: bool = False) -> str:
        # 0. Сборка сообщений
        payload = {
            "model": self._settings.ollama_chat_model,
            "stream": False,
            "think": reasoning,
            "keep_alive": self._settings.ollama_keep_alive,
            "options": {"num_ctx": self._settings.ollama_num_ctx, "num_predict": 1024, "temperature": 0.3},
            "messages": [
                {"role": "system", "content": system + ("\nВерни JSON по схеме. Поле answer содержит только готовый ответ пользователю, без внутренних рассуждений, планирования и тегов think." if schema is None else "")},
                {"role": "user", "content": user + ("" if reasoning else "\n/no_think")},
            ],
        }

        payload["format"] = schema or {"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"]}
        payload["options"]["temperature"] = 0
        payload["options"]["num_predict"] = max_tokens

        # 1. Запрос к Ollama
        async with self._client(timeout=max(self._timeout, 180.0)) as client:
            response = await client.post(f"{self._base}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        # 2. Ответ
        text = data.get("message", {}).get("content", "").strip()
        if "</think>" in text:
            text = text.split("</think>", 1)[1]
        if schema is None:
            text = json.loads(text)["answer"]
            if "</think>" in text:
                text = text.split("</think>", 1)[1]
        return text.strip()

    async def chat_stream(self, system: str, user: str):
        # Краткое объяснение подхода отделено от готового ответа.
        schema={"type":"object","properties":{"explanation":{"type":"string"},"answer":{"type":"string"}},"required":["explanation","answer"]}
        raw=await self.chat(system+" Верни explanation: краткое объяснение использованных материалов (1–2 предложения), без внутреннего монолога. answer: конкретный итоговый ответ. Не помещай размышления в answer.",user,max_tokens=1600,schema=schema)
        result=json.loads(raw)
        yield json.dumps({"message":{"explanation":result.get("explanation",""),"content":result["answer"]},"done":True},ensure_ascii=False)
