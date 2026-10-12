def valid_novel_llm_payload(
    *,
    title: str = "Тень над лесом",
    public_description: str = "Ведьма ищет пропавшего брата.",
    description: str = "Полное описание сюжета...",
    tone: str = "dark",
) -> dict:
    return {
        "title": title,
        "public_description": public_description,
        "description": description,
        "tone": tone,
    }
