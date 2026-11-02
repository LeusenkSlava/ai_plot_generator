from src.core.codex.models import OutfitEmotion, OutfitWithEmotions, TagKind
from src.outbound.codex.schemas import OutfitCatalogSchema, OutfitEmotionSchema


def outfit_emotion_payload(
    *,
    slug: str = "happy",
    name: str = "Happy",
    kind: TagKind | None = TagKind.BASE,
) -> dict:
    """Тег эмоции внутри сгруппированного элемента каталога (payload)."""
    return OutfitEmotionSchema(slug=slug, name=name, kind=kind).model_dump(mode="json")


def outfit_emotion_domain(
    *,
    slug: str = "happy",
    name: str = "Happy",
    kind: TagKind | None = TagKind.BASE,
) -> OutfitEmotion:
    """Тег эмоции внутри сгруппированного элемента каталога (домен)."""
    return OutfitEmotion(slug=slug, name=name, kind=kind)


def outfit_catalog_payload(
    *,
    outfit_tag: str = "casual",
    name: str = "Casual",
    emotions: list[dict] | None = None,
) -> dict:
    """Сгруппированный элемент каталога нарядов: style-тег + эмоции (payload)."""
    return OutfitCatalogSchema(
        outfit_tag=outfit_tag,
        name=name,
        emotions=[OutfitEmotionSchema(**e) for e in (emotions or [])],
    ).model_dump(mode="json")


def outfit_with_emotions_domain(
    *,
    outfit_tag: str = "casual",
    name: str = "Casual",
    emotions: list[OutfitEmotion] | None = None,
) -> OutfitWithEmotions:
    """Сгруппированный элемент каталога нарядов в доменном виде."""
    return OutfitWithEmotions(
        outfit_tag=outfit_tag,
        name=name,
        emotions=list(emotions) if emotions is not None else [],
    )
