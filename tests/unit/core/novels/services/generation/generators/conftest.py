import pytest

from src.core.novels.services.generation.generators.novel import NovelGenerator
from src.core.novels.services.generation.prompts.catalog import PromptCatalog
from tests.factories import valid_novel_llm_payload
from tests.factories.prompts import seed_all_prompts, seed_novel_prompt
from tests.fakes.core.novel.novel_service import FakeNovelService
from tests.fakes.outbound.ai.generator import FakeGenerator
from tests.fakes.outbound.codex.client import FakeCodexService
from tests.fakes.outbound.database.repositories.prompt_repository import (
    FakePromptRepository,
)


@pytest.fixture
def novel_service() -> FakeNovelService:
    return FakeNovelService()


@pytest.fixture
def codex() -> FakeCodexService:
    return FakeCodexService()


@pytest.fixture
def generator() -> FakeGenerator:
    return FakeGenerator()


@pytest.fixture
def prompt_repository() -> FakePromptRepository:
    """Пустое хранилище шаблонов: тест сам решает, какие промпты ему нужны."""
    return FakePromptRepository()


@pytest.fixture
def prompt_catalog(prompt_repository: FakePromptRepository) -> PromptCatalog:
    """Каталог с шаблонами всех генераторов (вариант default)."""
    return PromptCatalog(seed_all_prompts(prompt_repository))


@pytest.fixture
def sut(
    novel_service: FakeNovelService,
    codex: FakeCodexService,
    generator: FakeGenerator,
    prompt_repository: FakePromptRepository,
) -> NovelGenerator:
    seed_novel_prompt(prompt_repository)
    return NovelGenerator(
        novel_service=novel_service,
        codex_service=codex,
        generator=generator,
        prompt_catalog=PromptCatalog(prompt_repository),
    )


@pytest.fixture
def valid_llm_payload() -> dict:
    return valid_novel_llm_payload()
