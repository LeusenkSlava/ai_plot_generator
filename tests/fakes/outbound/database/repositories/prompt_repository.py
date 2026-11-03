from src.core.novels.models import Prompt


class FakePromptRepository:
    """Версии промптов в памяти: (key, variant) -> список версий."""

    def __init__(self) -> None:
        self._versions: dict[tuple[str, str], list[Prompt]] = {}

    def set_active(
        self,
        key: str,
        variant: str,
        *,
        system_template: str = "system json",
        user_template: str = "",
    ) -> Prompt:
        """Кладёт версию и делает её единственной активной (сид для теста)."""
        versions = self._versions.setdefault((key, variant), [])
        for existing in versions:
            existing.is_active = False
        prompt = Prompt(
            id=len(versions) + 1,
            created_at=None,
            updated_at=None,
            key=key,
            variant=variant,
            version=len(versions) + 1,
            system_template=system_template,
            user_template=user_template,
            is_active=True,
        )
        versions.append(prompt)
        return prompt

    async def get_active(self, key: str, variant: str) -> Prompt | None:
        for prompt in self._versions.get((key, variant), []):
            if prompt.is_active:
                return prompt
        return None

    async def add(self, prompt: Prompt) -> Prompt:
        stored = self.set_active(
            prompt.key,
            prompt.variant,
            system_template=prompt.system_template,
            user_template=prompt.user_template,
        )
        return stored

    async def list_versions(self, key: str, variant: str) -> list[Prompt]:
        return list(self._versions.get((key, variant), []))
