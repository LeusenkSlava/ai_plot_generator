"""Персональная библиотека: выборки и удаление только по автору.

Пользователи живут в my_choice_api, здесь хранится лишь ``author_id``. Чужая
новелла должна быть неотличима от несуществующей (``None`` → 404 у роутера),
чтобы не раскрывать факт её существования.
"""

from src.core.novels.services.crud import NovelService
from tests.factories import novel_domain
from tests.fakes.outbound.database.repositories.novel_repository import (
    FakeNovelRepository,
)


async def _seeded_service() -> tuple[NovelService, int, int, int]:
    repository = FakeNovelRepository()
    own = await repository.add(novel_domain(title="Своя", author_id=1))
    foreign = await repository.add(novel_domain(title="Чужая", author_id=2))
    system = await repository.add(novel_domain(title="Системная", author_id=1))
    return NovelService(repository), own.id, foreign.id, system.id


class TestNovelListScope:
    async def test_list_returns_only_authors_novels(self):
        service, own_id, _foreign_id, system_id = await _seeded_service()

        novels, total = await service.list(limit=20, offset=0, author_id=1)

        assert total == 2
        assert {novel.id for novel in novels} == {own_id, system_id}

    async def test_total_counts_only_authors_novels(self):
        service, *_ = await _seeded_service()

        _, total = await service.list(limit=1, offset=0, author_id=2)

        assert total == 1

    async def test_list_without_author_is_unscoped_for_internal_callers(self):
        service, *_ = await _seeded_service()

        novels, total = await service.list(limit=20, offset=0)

        assert total == 3
        assert len(novels) == 3


class TestNovelGetScope:
    async def test_get_returns_own_novel(self):
        service, own_id, _foreign_id, _system_id = await _seeded_service()

        novel = await service.get(own_id, author_id=1)

        assert novel is not None
        assert novel.id == own_id

    async def test_get_hides_foreign_novel(self):
        service, _own_id, foreign_id, _system_id = await _seeded_service()

        assert await service.get(foreign_id, author_id=1) is None

    async def test_get_without_author_is_unscoped_for_internal_callers(self):
        service, _own_id, foreign_id, _system_id = await _seeded_service()

        assert await service.get(foreign_id) is not None


class TestNovelDeleteScope:
    async def test_delete_removes_own_novel(self):
        service, own_id, _foreign_id, _system_id = await _seeded_service()

        assert await service.delete(own_id, author_id=1) is True
        assert await service.get(own_id, author_id=1) is None

    async def test_delete_keeps_foreign_novel(self):
        service, _own_id, foreign_id, _system_id = await _seeded_service()

        assert await service.delete(foreign_id, author_id=1) is False
        assert await service.get(foreign_id, author_id=2) is not None
