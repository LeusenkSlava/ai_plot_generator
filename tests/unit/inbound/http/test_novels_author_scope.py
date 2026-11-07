"""HTTP-доступ к новеллам ai_plot.

Опубликованная новелла читается без заголовка ``X-User-Id``; неопубликованная —
только автором. Публикация и удаление требуют заголовок автора. Чужая
неопубликованная новелла неотличима от несуществующей (404).
"""

import dataclasses
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.core.novels.exceptions import NovelNotFoundError
from src.core.novels.services.playback import PlaybackResult, PlaybackStatus
from src.inbound.http.novels.dependencies import (
    get_author_id,
    get_novel_playback_service,
    get_novel_service,
    get_optional_author_id,
)
from src.inbound.http.novels.router import router
from tests.factories import novel_domain


def _novel(novel_id: int, author_id: int, *, is_published: bool = False):
    return novel_domain(
        id=novel_id,
        title=f"Новелла {novel_id}",
        author_id=author_id,
        is_published=is_published,
        published_at=datetime(2026, 11, 7, tzinfo=UTC) if is_published else None,
        created_at=datetime(2026, 11, 7, tzinfo=UTC),
        updated_at=datetime(2026, 11, 7, tzinfo=UTC),
    )


class _FakeNovelService:
    def __init__(self, novels) -> None:
        self._novels = {novel.id: novel for novel in novels}

    async def get_visible(self, novel_id: int, author_id: int | None = None):
        novel = self._novels.get(novel_id)
        if novel is None:
            return None
        if novel.is_published:
            return novel
        if author_id is not None and novel.author_id == author_id:
            return novel
        return None

    async def list(self, limit: int, offset: int, author_id: int | None = None):
        novels = [
            novel
            for novel in self._novels.values()
            if novel.is_published
            or (author_id is not None and novel.author_id == author_id)
        ]
        return novels[offset : offset + limit], len(novels)

    async def delete(self, novel_id: int, author_id: int | None = None) -> bool:
        novel = self._novels.get(novel_id)
        if novel is None:
            return False
        if author_id is not None and novel.author_id != author_id:
            return False
        self._novels.pop(novel_id)
        return True

    async def set_published(
        self, novel_id: int, author_id: int, is_published: bool
    ):
        novel = self._novels.get(novel_id)
        if novel is None or novel.author_id != author_id:
            return None
        published_at = novel.published_at
        if not is_published:
            published_at = None
        elif published_at is None:
            published_at = datetime(2026, 11, 7, tzinfo=UTC)
        updated = dataclasses.replace(
            novel, is_published=is_published, published_at=published_at
        )
        self._novels[novel_id] = updated
        return updated


class _FakePlaybackService:
    def __init__(self, novels) -> None:
        self.calls: list[tuple[int, int | None, int | None]] = []
        self._novels = {novel.id: novel for novel in novels}

    async def next(
        self,
        novel_id: int,
        dialogue_line_id: int | None,
        author_id: int | None = None,
    ) -> PlaybackResult:
        self.calls.append((novel_id, dialogue_line_id, author_id))
        novel = self._novels.get(novel_id)
        if novel is None:
            raise NovelNotFoundError(novel_id)
        if not novel.is_published and novel.author_id != author_id:
            raise NovelNotFoundError(novel_id)
        return PlaybackResult(status=PlaybackStatus.FINISHED)


@pytest.fixture
def novels():
    return [
        _novel(1, author_id=1),
        _novel(2, author_id=2),
        _novel(3, author_id=2, is_published=True),
    ]


@pytest.fixture
def playback(novels) -> _FakePlaybackService:
    return _FakePlaybackService(novels)


@pytest.fixture
def client(novels, playback) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    # Один экземпляр на приложение: удаление/публикация видны следующим запросам.
    service = _FakeNovelService(novels)
    app.dependency_overrides[get_novel_service] = lambda: service
    app.dependency_overrides[get_novel_playback_service] = lambda: playback
    return TestClient(app)


class TestAuthorHeaders:
    def test_optional_header_absent_means_anonymous(self):
        assert get_optional_author_id(None) is None

    def test_optional_header_returned_as_author_id(self):
        assert get_optional_author_id(42) == 42

    def test_optional_non_positive_header_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            get_optional_author_id(0)

        assert exc_info.value.status_code == 401

    def test_missing_header_rejected_for_writes(self):
        with pytest.raises(HTTPException) as exc_info:
            get_author_id(None)

        assert exc_info.value.status_code == 401

    def test_non_positive_header_rejected_for_writes(self):
        with pytest.raises(HTTPException):
            get_author_id(0)

    def test_header_returned_as_author_id(self):
        assert get_author_id(42) == 42


class TestNovelListVisibility:
    def test_list_anonymous_returns_only_published(self, client):
        response = client.get("/novels/")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert [item["id"] for item in body["items"]] == [3]
        assert body["items"][0]["is_published"] is True

    def test_list_author_returns_own_and_published(self, client):
        response = client.get("/novels/", headers={"X-User-Id": "1"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert {item["id"] for item in body["items"]} == {1, 3}


class TestNovelGetVisibility:
    def test_get_published_novel_without_header(self, client):
        response = client.get("/novels/3")

        assert response.status_code == 200
        assert response.json()["id"] == 3

    def test_get_unpublished_novel_without_header_is_404(self, client):
        assert client.get("/novels/1").status_code == 404

    def test_get_own_novel_with_header(self, client):
        assert client.get("/novels/1", headers={"X-User-Id": "1"}).status_code == 200

    def test_get_foreign_unpublished_novel_is_404(self, client):
        assert client.get("/novels/2", headers={"X-User-Id": "1"}).status_code == 404

    def test_get_foreign_published_novel_with_header(self, client):
        response = client.get("/novels/3", headers={"X-User-Id": "1"})

        assert response.status_code == 200


class TestNovelDelete:
    def test_delete_requires_author_header(self, client):
        assert client.delete("/novels/1").status_code == 401

    def test_delete_foreign_novel_is_404_and_keeps_it(self, client):
        response = client.delete("/novels/2", headers={"X-User-Id": "1"})

        assert response.status_code == 404
        assert client.get("/novels/2", headers={"X-User-Id": "2"}).status_code == 200

    def test_delete_own_novel(self, client):
        response = client.delete("/novels/1", headers={"X-User-Id": "1"})

        assert response.status_code == 204
        assert client.get("/novels/1", headers={"X-User-Id": "1"}).status_code == 404


class TestPlaybackVisibility:
    def test_start_published_novel_without_header(self, client, playback):
        response = client.get("/novels/start/3")

        assert response.status_code == 200
        assert response.json() == {"status": "finished"}
        assert playback.calls == [(3, None, None)]

    def test_start_unpublished_novel_without_header_is_404(self, client, playback):
        response = client.get("/novels/start/1")

        assert response.status_code == 404
        assert playback.calls == [(1, None, None)]

    def test_start_passes_author_id(self, client, playback):
        response = client.get("/novels/start/1", headers={"X-User-Id": "1"})

        assert response.status_code == 200
        assert playback.calls == [(1, None, 1)]

    def test_start_foreign_novel_is_404(self, client, playback):
        response = client.get("/novels/start/2", headers={"X-User-Id": "1"})

        assert response.status_code == 404
        assert playback.calls == [(2, None, 1)]


class TestPublication:
    def test_publish_requires_author_header(self, client):
        assert client.post("/novels/1/publish").status_code == 401

    def test_author_publishes_novel(self, client):
        response = client.post("/novels/1/publish", headers={"X-User-Id": "1"})

        assert response.status_code == 200
        body = response.json()
        assert body["is_published"] is True
        assert body["published_at"] is not None
        # Теперь новелла читается анонимно.
        assert client.get("/novels/1").status_code == 200

    def test_foreign_novel_cannot_be_published(self, client):
        response = client.post("/novels/2/publish", headers={"X-User-Id": "1"})

        assert response.status_code == 404
        assert client.get("/novels/2").status_code == 404

    def test_author_unpublishes_novel(self, client):
        response = client.delete("/novels/3/publish", headers={"X-User-Id": "2"})

        assert response.status_code == 200
        body = response.json()
        assert body["is_published"] is False
        assert body["published_at"] is None
        assert client.get("/novels/3").status_code == 404
