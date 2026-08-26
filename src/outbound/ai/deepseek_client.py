import json
import logging
from openai import APIError, APIConnectionError
from openai import AsyncOpenAI


logger = logging.getLogger(__name__)


class DeepSeekNovelGenerator:
    def __init__(self, client: AsyncOpenAI):
        self._client = client

    async def generate(self, prompt: list) -> dict:
        try:
            response = await self._client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=prompt,
                response_format={"type": "json_object"},
                temperature=0.9,
            )
        except (APIError, APIConnectionError) as e:
            logger.error("DeepSeekNovelGenerator.generate_j: {}".format(e))
            raise RuntimeError(f"DeepSeek API error: {e}") from e

        content = response.choices[0].message.content
        try:
            data = json.loads(content)
            return data
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"Invalid DeepSeek response format: {e}") from e
