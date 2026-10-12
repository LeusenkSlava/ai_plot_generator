from datetime import datetime

from src.core.novels.models import Novel


def novel_domain(
    *,
    id: int | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    title: str = "Тень над лесом",
    public_description: str = "Ведьма ищет пропавшего брата.",
    description: str = "Полное описание сюжета...",
    tone: str = "dark",
    universe_id: int | None = None,
) -> Novel:
    return Novel(
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        title=title,
        public_description=public_description,
        description=description,
        tone=tone,
        universe_id=universe_id,
    )
