from tests.unit.outbound.codex.constants import BASE_URL


def universe_url(universe_id: int) -> str:
    return f"{BASE_URL}/universes/{universe_id}"


def characters_url(universe_id: int) -> str:
    return f"{BASE_URL}/universes/{universe_id}/characters"


def backgrounds_url(universe_id: int) -> str:
    return f"{BASE_URL}/universes/{universe_id}/backgrounds"


def sprites_url(character_id: int) -> str:
    return f"{BASE_URL}/characters/{character_id}/sprites"


def emotions_url(character_id: int) -> str:
    return f"{BASE_URL}/characters/{character_id}/emotions"


def outfits_url(sprite_id: int) -> str:
    return f"{BASE_URL}/sprites/{sprite_id}/outfits"
