import json
import logging
import time

from openai import APIConnectionError, APIError, AsyncOpenAI

from src.outbound.ai.llm_log import log_llm_call

logger = logging.getLogger(__name__)

MODEL = "deepseek-v4-flash"


class DeepSeekGenerator:
    def __init__(self, client: AsyncOpenAI):
        self._client = client

    async def generate(self, prompt: list) -> dict:
        started = time.monotonic()
        try:
            response = await self._client.chat.completions.create(
                model=MODEL,
                messages=prompt,
                response_format={"type": "json_object"},
                temperature=0.9,
            )
        except (APIError, APIConnectionError) as e:
            log_llm_call(
                model=MODEL,
                messages=prompt,
                response=None,
                prompt_tokens=None,
                completion_tokens=None,
                duration_s=time.monotonic() - started,
                error=str(e),
            )
            logger.error(f"DeepSeekGenerator.generate_j: {e}")
            raise RuntimeError(f"DeepSeek API error: {e}") from e

        content = response.choices[0].message.content
        usage = response.usage
        log_llm_call(
            model=MODEL,
            messages=prompt,
            response=content,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            duration_s=time.monotonic() - started,
            extra={
                "cache_hit_tokens": getattr(usage, "prompt_cache_hit_tokens", None),
            },
        )
        try:
            data = json.loads(content)
            return data
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"Invalid DeepSeek response format: {e}") from e
