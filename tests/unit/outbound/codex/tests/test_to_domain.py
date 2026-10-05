from src.core.codex.models import (
    Background,
    CodexCharacter,
    Tag,
    TagType,
    Universe,
)
from src.outbound.codex.codex_client import HttpCodexClient
from src.outbound.codex.schemas import (
    BackgroundSchema,
    CharacterSchema,
    TagSchema,
    UniverseSchema,
)
from tests.unit.outbound.codex.factories import tag_domain


class TestToDomainWithoutTags:
    def test_universe_maps_all_fields(self):
        schema = UniverseSchema(id=1, slug="mir-tmy", title="Мир Тьмы", description="D")

        result = HttpCodexClient._to_domain(schema, Universe)

        assert result == Universe(
            id=1, slug="mir-tmy", title="Мир Тьмы", description="D"
        )


class TestToDomainWithTags:
    def test_tags_converted_to_domain_models(self):
        schema = CharacterSchema(
            id=1,
            universe_id=1,
            slug="alice",
            name="Алиса",
            description="Ведьма",
            tags=[
                TagSchema(id=1, type=TagType.ARCHETYPE, slug="warrior", name="Warrior"),
                TagSchema(id=2, type=TagType.EMOTION, slug="happy", name="Happy"),
            ],
        )

        result = HttpCodexClient._to_domain(schema, CodexCharacter)

        assert result.tags == [
            tag_domain(id=1, type=TagType.ARCHETYPE, slug="warrior", name="Warrior"),
            tag_domain(id=2, type=TagType.EMOTION, slug="happy", name="Happy"),
        ]
        assert all(isinstance(t, Tag) for t in result.tags)

    def test_empty_tags_stays_empty(self):
        schema = BackgroundSchema(
            id=1,
            universe_id=1,
            slug="forest",
            description="Лес",
            asset_key="bg/forest.png",
            tags=[],
        )

        result = HttpCodexClient._to_domain(schema, Background)

        assert result.tags == []
