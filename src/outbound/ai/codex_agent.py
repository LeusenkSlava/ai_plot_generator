import logging
from dataclasses import asdict, dataclass

from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.deepseek import DeepSeekProvider

from src.core.codex.exceptions import CodexUnavailableError
from src.core.codex.services import CodexService

logger = logging.getLogger(__name__)

_INSTRUCTIONS = """
Ты — исследователь базы знаний Codex для генератора визуальных новелл.
По пожеланию пользователя изучи Codex с помощью инструментов:
1. Вселенная уже выбрана пользователем, её id передан в запросе — другие вселенные не используй.
2. Получи описание вселенной (get_universes), её персонажей и фоны.
3. Для ключевых персонажей при необходимости получи спрайты, эмоции и наряды.
Не выдумывай данные — используй только то, что вернули инструменты.
В ответе дай краткую структурированную выжимку на русском языке: вселенная (id, slug, описание),
подходящие персонажи (id, slug, имя, описание, манера речи), подходящие фоны (id, slug, описание),
доступные эмоции/наряды (slug). Если ничего подходящего нет — так и напиши.
"""


@dataclass
class CodexDeps:
    codex: CodexService


def _dump(items: list) -> list[dict]:
    return [asdict(i) for i in items]


def _build_agent(client: AsyncOpenAI, model_name: str) -> Agent[CodexDeps, str]:
    model = OpenAIChatModel(model_name, provider=DeepSeekProvider(openai_client=client))
    agent = Agent(model, deps_type=CodexDeps, output_type=str, instructions=_INSTRUCTIONS)

    @agent.tool
    async def get_universes(ctx: RunContext[CodexDeps]) -> list[dict]:
        """Список всех вселенных Codex."""
        return _dump(await ctx.deps.codex.get_universes())

    @agent.tool
    async def get_characters(ctx: RunContext[CodexDeps], universe_id: int) -> list[dict]:
        """Персонажи вселенной."""
        return _dump(await ctx.deps.codex.get_characters(universe_id))

    @agent.tool
    async def get_backgrounds(ctx: RunContext[CodexDeps], universe_id: int) -> list[dict]:
        """Фоны (локации) вселенной."""
        return _dump(await ctx.deps.codex.get_backgrounds(universe_id))

    @agent.tool
    async def get_sprites(ctx: RunContext[CodexDeps], character_id: int) -> list[dict]:
        """Спрайты персонажа."""
        return _dump(await ctx.deps.codex.get_sprites(character_id))

    @agent.tool
    async def get_emotions(ctx: RunContext[CodexDeps], character_id: int) -> list[dict]:
        """Эмоции персонажа."""
        return _dump(await ctx.deps.codex.get_emotions(character_id))

    @agent.tool
    async def get_outfits(ctx: RunContext[CodexDeps], sprite_id: int) -> list[dict]:
        """Наряды спрайта."""
        return _dump(await ctx.deps.codex.get_outfits(sprite_id))

    return agent


class CodexResearcher:
    """Реализует CodexResearcherProtocol: pydantic-ai агент, который сам ходит в Codex."""

    def __init__(
        self,
        client: AsyncOpenAI,
        codex_service: CodexService,
        model_name: str = "deepseek-v4-flash",
    ):
        self._agent = _build_agent(client, model_name)
        self._deps = CodexDeps(codex=codex_service)

    async def research(self, user_prompt: str, universe_id: int) -> str:
        prompt = f"universe_id: {universe_id}\nПожелание пользователя: {user_prompt}"
        try:
            result = await self._agent.run(prompt, deps=self._deps)
        except CodexUnavailableError:
            raise
        except Exception as e:
            logger.error(f"CodexResearcher.research: {e}")
            raise RuntimeError(f"Codex research failed: {e}") from e
        return result.output
