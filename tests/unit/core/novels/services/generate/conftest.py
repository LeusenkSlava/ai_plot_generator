import pytest

from src.core.novels.services.generate.novel import NovelGenerator
from tests.factories import valid_novel_llm_payload
from tests.fakes.core.novel.novel_service import FakeNovelService
from tests.fakes.outbound.ai.generator import FakeGenerator
from tests.fakes.outbound.codex.client import FakeCodexService


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
def sut(
    novel_service: FakeNovelService,
    codex: FakeCodexService,
    generator: FakeGenerator,
) -> NovelGenerator:
    return NovelGenerator(
        novel_service=novel_service,
        codex_service=codex,
        generator=generator,
    )


@pytest.fixture
def valid_llm_payload() -> dict:
    return valid_novel_llm_payload()
