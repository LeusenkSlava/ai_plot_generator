"""HTTP-скоуп новелл по автору: заголовок ``X-User-Id`` обязателен.

Шлюз (my_choice_api) уже проверил JWT и передаёт сюда id учётки. Без заголовка
запрос отклоняется, а чужая новелла неотличима от несуществующей (404).
"""

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
)
from src.inbound.http.novels.router import router
from tests.factories import novel_domain


def _novel(novel_id: int, author_id: int):
    return novel_domain(
        id=novel_id,
        title=f"Новелла {novel_id}",
        author_id=author_id,
        created_at=datetime(2026, 11, 7, tzinfo=UTC),
        updated_at=datetime(2026, 11, 7, tzinfo=UTC),
    )


class _FakeNovelService:
    def __init__(self, novels) -> None:
        self._novels = {novel.id: novel for novel in novels}

    async def get(self, novel_id: int, author_id: int | None = None):
        novel = self._novels.get(novel_id)
        if novel is None:
            return None
        if author_id is not None and novel.author_id != author_id:
            return None
        return novel

    async def list(
        self, limit: int, offset: int, author_id: int | None = None
    ):
        novels = [
            novel
            for novel in self._novels.values()
            if author_id is None or novel.author_id == author_id
        ]
        return novels[offset : offset + limit], len(novels)

    async def delete(
        self, novel_id: int, author_id: int | None = None
    ) -> bool:
        novel = self._novels.get(novel_id)
        if novel is None:
            return False
        if author_id is not None and novel.author_id != author_id:
            return False
        self._novels.pop(novel_id)
        return True


class _FakePlaybackService:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int | None, int | None]] = []
        self._authors = {1: 1, 2: 2}

    async def next(
        self,
        novel_id: int,
        dialogue_line_id: int | None,
        author_id: int | None = None,
    ) -> PlaybackResult:
        self.calls.append((novel_id, dialogue_line_id, author_id))
        if self._authors.get(novel_id) != author_id:
            raise NovelNotFoundError(novel_id)
        return PlaybackResult(status=PlaybackStatus.FINISHED)


@pytest.fixture
def novels():
    return [_novel(1, author_id=1), _novel(2, author_id=2)]


@pytest.fixture
def playback() -> _FakePlaybackService:
    return _FakePlaybackService()


@pytest.fixture
def client(novels, playback) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    # Один экземпляр на приложение: удаление в одном запросе видно следующему.
    service = _FakeNovelService(novels)
    app.dependency_overrides[get_novel_service] = lambda: service
    app.dependency_overrides[get_novel_playback_service] = lambda: playback
    return TestClient(app)


class TestAuthorHeader:
    def test_missing_header_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            get_author_id(None)

        assert exc_info.value.status_code == 401

    def test_non_positive_header_rejected(self):
        with pytest.raises(HTTPException):
            get_author_id(0)

    def test_header_returned_as_author_id(self):
        assert get_author_id(42) == 42


class TestNovelsScopedByAuthor:
    def test_list_requires_author_header(self, client):
        assert client.get("/novels/").status_code == 401

    def test_list_returns_only_authors_novels(self, client):
        response = client.get("/novels/", headers={"X-User-Id": "1"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert [item["id"] for item in body["items"]] == [1]
        assert body["items"][0]["author_id"] == 1

    def test_get_own_novel(self, client):
        response = client.get("/novels/1", headers={"X-User-Id": "1"})

        assert response.status_code == 200
        assert response.json()["author_id"] == 1

    def test_get_foreign_novel_is_404(self, client):
        response = client.get("/novels/2", headers={"X-User-Id": "1"})

        assert response.status_code == 404

    def test_delete_foreign_novel_is_404_and_keeps_it(self, client):
        response = client.delete("/novels/2", headers={"X-User-Id": "1"})

        assert response.status_code == 404
        assert (
            client.get("/novels/2", headers={"X-User-Id": "2"}).status_code
            == 200
        )

    def test_delete_own_novel(self, client):
        response = client.delete("/novels/1", headers={"X-User-Id": "1"})

        assert response.status_code == 204
        assert (
            client.get("/novels/1", headers={"X-User-Id": "1"}).status_code
            == 404
        )


class TestPlaybackScopedByAuthor:
    def test_start_passes_author_id(self, client, playback):
        response = client.get(
            "/novels/start/1", headers={"X-User-Id": "1"}
        )

        assert response.status_code == 200
        assert response.json() == {"status": "finished"}
        assert playback.calls == [(1, None, 1)]

    def test_start_foreign_novel_is_404(self, client, playback):
        response = client.get(
            "/novels/start/2", headers={"X-User-Id": "1"}
        )

        assert response.status_code == 404
        assert playback.calls == [(2, None, 1)]
