from typing import Protocol

from src.core.codex.models import (
    Background,
    BackgroundMatchItem,
    BackgroundTags,
    CodexCharacter,
    OutfitWithEmotions,
    Universe,
    VisualMatch,
)


class CodexClientProtocol(Protocol):
    async def list_universes(self) -> list[Universe]: ...
    async def get_universe(self, universe_id: int) -> Universe: ...
    async def get_characters(self, universe_id: int) -> list[CodexCharacter]: ...
    async def get_backgrounds(self, universe_id: int) -> list[Background]: ...
    async def get_background_tags(self, universe_id: int) -> BackgroundTags: ...
    async def match_background(
        self, universe_id: int, tags: list[str]
    ) -> Background | None: ...
    async def match_backgrounds_batch(
        self, items: list[BackgroundMatchItem]
    ) -> dict[int, Background | None]: ...
    async def get_outfits_with_emotions_batch(
        self, character_ids: list[int]
    ) -> dict[int, list[OutfitWithEmotions]]: ...
    async def match_visual(
        self, character_id: int, outfit_tag: str, emotion_tags: list[str]
    ) -> VisualMatch | None: ...
