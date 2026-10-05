from tests.fakes.core.novel.novel_service import FakeNovelService
from tests.fakes.outbound.ai.generator import FakeGenerator
from tests.fakes.outbound.codex.client import FakeCodexService
from tests.fakes.outbound.database.repositories.novel_repository import (
    FakeNovelRepository,
)

__all__ = [
    "FakeCodexService",
    "FakeGenerator",
    "FakeNovelRepository",
    "FakeNovelService",
]
