"""Доступ к новеллам: опубликованные видны всем, свои — автору.

Пользователи живут в my_choice_api, здесь хранится лишь ``author_id``. Чужая
неопубликованная новелла должна быть неотличима от несуществующей
(``None`` → 404 у роутера), чтобы не раскрывать факт её существования.
"""

from datetime import UTC, datetime

from src.core.novels.services.crud import NovelService
from tests.factories import novel_domain
from tests.fakes.outbound.database.repositories.novel_repository import (
    FakeNovelRepository,
)


async def _seeded_service() -> tuple[NovelService, int, int, int]:
    repository = FakeNovelRepository()
    own = await repository.add(novel_domain(title="Своя", author_id=1))
    foreign = await repository.add(novel_domain(title="Чужая", author_id=2))
    published = await repository.add(
        novel_domain(title="Опубликованная", author_id=3, is_published=True)
    )
    return NovelService(repository), own.id, foreign.id, published.id


class TestNovelListVisibility:
    async def test_author_sees_own_and_published(self):
        service, own_id, _foreign_id, published_id = await _seeded_service()

        novels, total = await service.list(limit=20, offset=0, author_id=1)

        assert total == 2
        assert {novel.id for novel in novels} == {own_id, published_id}

    async def test_anonymous_sees_only_published(self):
        service, _own_id, _foreign_id, published_id = await _seeded_service()

        novels, total = await service.list(limit=20, offset=0)

        assert total == 1
        assert {novel.id for novel in novels} == {published_id}

    async def test_total_counts_visible_novels(self):
        service, *_ = await _seeded_service()

        _, total = await service.list(limit=1, offset=0, author_id=2)

        assert total == 2


class TestNovelGetVisibility:
    async def test_author_gets_own_novel(self):
        service, own_id, _foreign_id, _published_id = await _seeded_service()

        novel = await service.get_visible(own_id, author_id=1)

        assert novel is not None
        assert novel.id == own_id

    async def test_foreign_unpublished_novel_is_hidden(self):
        service, _own_id, foreign_id, _published_id = await _seeded_service()

        assert await service.get_visible(foreign_id, author_id=1) is None
        assert await service.get_visible(foreign_id, author_id=None) is None

    async def test_published_novel_is_visible_to_everyone(self):
        service, _own_id, _foreign_id, published_id = await _seeded_service()

        assert await service.get_visible(published_id, author_id=1) is not None
        assert await service.get_visible(published_id, author_id=None) is not None

    async def test_internal_get_without_author_is_unscoped(self):
        service, _own_id, foreign_id, _published_id = await _seeded_service()

        assert await service.get(foreign_id) is not None


class TestNovelDeleteScope:
    async def test_delete_removes_own_novel(self):
        service, own_id, _foreign_id, _published_id = await _seeded_service()

        assert await service.delete(own_id, author_id=1) is True
        assert await service.get(own_id, author_id=1) is None

    async def test_delete_keeps_foreign_novel(self):
        service, _own_id, foreign_id, _published_id = await _seeded_service()

        assert await service.delete(foreign_id, author_id=1) is False
        assert await service.get(foreign_id, author_id=2) is not None


class TestNovelPublication:
    async def test_author_publishes_own_novel(self):
        service, own_id, _foreign_id, _published_id = await _seeded_service()

        novel = await service.set_published(own_id, author_id=1, is_published=True)

        assert novel is not None
        assert novel.is_published is True
        assert novel.published_at is not None

    async def test_foreign_novel_cannot_be_published(self):
        service, _own_id, foreign_id, _published_id = await _seeded_service()

        assert (
            await service.set_published(foreign_id, author_id=1, is_published=True)
            is None
        )

    async def test_republish_keeps_published_at(self):
        repository = FakeNovelRepository()
        own = await repository.add(novel_domain(author_id=1))
        service = NovelService(repository)

        first = await service.set_published(own.id, author_id=1, is_published=True)
        second = await service.set_published(own.id, author_id=1, is_published=True)

        assert first.published_at == second.published_at

    async def test_unpublish_clears_published_at(self):
        repository = FakeNovelRepository()
        own = await repository.add(
            novel_domain(
                author_id=1,
                is_published=True,
                published_at=datetime(2026, 11, 7, tzinfo=UTC),
            )
        )
        service = NovelService(repository)

        novel = await service.set_published(own.id, author_id=1, is_published=False)

        assert novel.is_published is False
        assert novel.published_at is None
