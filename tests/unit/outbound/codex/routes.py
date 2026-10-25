from tests.unit.outbound.codex.constants import BASE_URL


def universe_url(universe_id: int) -> str:
    return f"{BASE_URL}/universes/{universe_id}"


def characters_url(universe_id: int) -> str:
    return f"{BASE_URL}/universes/{universe_id}/characters"


def backgrounds_url(universe_id: int) -> str:
    return f"{BASE_URL}/universes/{universe_id}/backgrounds"


def visuals_match_url(character_id: int) -> str:
    return f"{BASE_URL}/characters/{character_id}/visuals/match"


def outfits_with_emotions_batch_url() -> str:
    return f"{BASE_URL}/characters/outfits-with-emotions/batch"
