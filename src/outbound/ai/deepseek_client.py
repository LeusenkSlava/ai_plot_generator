import json
import logging
import time

from json_repair import repair_json
from openai import APIConnectionError, APIError, AsyncOpenAI

from src.outbound.ai.llm_log import log_llm_call

logger = logging.getLogger(__name__)

MODEL = "deepseek-v4-flash"


def _is_truncated(text: str) -> bool:
    """True, если JSON структурно неполон (обрезан по лимиту токенов).

    Считаем обрезанным только незакрытую строку или незакрытые ``{``/``[``.
    Лишние закрывающие скобки и прочий мусор сюда не относятся — их оставляем
    на json-repair (или на ретрай, если и он не справится).
    """
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch == "}":
            if stack and stack[-1] == "}":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "]":
                stack.pop()
    return in_string or bool(stack)


class DeepSeekGenerator:
    def __init__(self, client: AsyncOpenAI, temperature: float = 0.9):
        self._client = client
        self._temperature = temperature

    async def generate(
        self,
        prompt: list,
        think: bool = True,
        reasoning_effort: str | None = None,
    ) -> dict:
        started = time.monotonic()
        request = {
            "model": MODEL,
            "messages": prompt,
            "response_format": {"type": "json_object"},
            "temperature": self._temperature,
            # thinking mode: enabled/disabled, см. api-docs.deepseek.com/guides/thinking_mode
            "extra_body": {"thinking": {"type": "enabled" if think else "disabled"}},
        }
        # reasoning_effort — top-level параметр (не в extra_body), действует при enabled
        if reasoning_effort is not None:
            request["reasoning_effort"] = reasoning_effort
        try:
            response = await self._client.chat.completions.create(**request)
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
        reasoning_tokens = None
        if usage is not None:
            details = getattr(usage, "completion_tokens_details", None)
            if details is not None:
                reasoning_tokens = getattr(details, "reasoning_tokens", None)

        data: dict | None = None
        json_repaired = False
        parse_error: Exception | None = None
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, KeyError) as e:
            parse_error = e
            if not _is_truncated(content):
                try:
                    data = json.loads(repair_json(content))
                    json_repaired = True
                    parse_error = None
                except Exception:
                    pass  # parse_error уже хранит исходную ошибку

        extra = {
            "cache_hit_tokens": getattr(usage, "prompt_cache_hit_tokens", None),
            "reasoning_tokens": reasoning_tokens,
        }
        if json_repaired:
            extra["json_repaired"] = True
        log_llm_call(
            model=MODEL,
            messages=prompt,
            response=content,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            duration_s=time.monotonic() - started,
            error="invalid json" if parse_error is not None else None,
            extra=extra,
        )

        if parse_error is not None:
            raise RuntimeError(
                f"Invalid DeepSeek response format: {parse_error}"
            ) from parse_error
        return data
