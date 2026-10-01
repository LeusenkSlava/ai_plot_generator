from typing import Protocol

from src.core.codex.models import (
    Background,
    CodexCharacter,
    Emotion,
    Outfit,
    Sprite,
    Universe,
)


class CodexClientProtocol(Protocol):
    async def get_universes(self) -> list[Universe]: ...
    async def get_characters(self, universe_id: int) -> list[CodexCharacter]: ...
    async def get_backgrounds(self, universe_id: int) -> list[Background]: ...
    async def get_sprites(self, character_id: int) -> list[Sprite]: ...
    async def get_emotions(self, character_id: int) -> list[Emotion]: ...
    async def get_outfits(self, sprite_id: int) -> list[Outfit]: ...


class CodexResearcherProtocol(Protocol):
    async def research(self, user_prompt: str, universe_id: int) -> str:
        """Собирает из Codex выжимку знаний о вселенной, релевантную пожеланию пользователя."""
        ...
