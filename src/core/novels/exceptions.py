class NovelNotFoundError(Exception):
    def __init__(self, novel_id: int):
        self.novel_id = novel_id
        super().__init__(f"Novel {novel_id} not found")


class GenerationError(Exception):
    """AI не смог сгенерировать описание."""


class NovelGenerationFailedError(GenerationError):
    """Сбой генерации новеллы на одном из шагов саги.

    Несёт ``novel_id`` частично созданной новеллы (если она уже закоммичена),
    чтобы вызывающий выполнил компенсацию — удалил её каскадом.
    """

    def __init__(self, novel_id: int | None, message: str):
        self.novel_id = novel_id
        super().__init__(message)


class GenerationInProgressError(Exception):
    """Другой воркер ещё обрабатывает этот job — повторить позже (ретрай-сигнал)."""


class DialogueLineNotFoundError(Exception):
    def __init__(self, dialogue_line_id: int):
        self.dialogue_line_id = dialogue_line_id
        super().__init__(f"Dialogue line {dialogue_line_id} not found")


class CharacterNotFoundError(Exception):
    def __init__(self, character_id: int):
        self.character_id = character_id
        super().__init__(f"Character {character_id} not found")


class SceneNotFoundError(Exception):
    def __init__(self, scene_id: int):
        self.scene_id = scene_id
        super().__init__(f"Scene {scene_id} not found")


class NovelFinishedError(Exception):
    """Роадмап новеллы пройден — следующей сцены не будет."""

    def __init__(self, novel_id: int):
        self.novel_id = novel_id
        super().__init__("novel_finished")


class SceneOrderError(Exception):
    """Запрошена сцена не по порядку: предыдущая ещё не сгенерирована."""

    def __init__(self, novel_id: int, requested: str, expected: str):
        self.novel_id = novel_id
        self.requested = requested
        self.expected = expected
        super().__init__(
            f"Scene {requested} of novel {novel_id} cannot be generated: "
            f"next scene to generate is {expected}"
        )


class RoadmapChoiceNotFoundError(Exception):
    def __init__(self, roadmap_choice_id: int):
        self.roadmap_choice_id = roadmap_choice_id
        super().__init__(f"Roadmap choice {roadmap_choice_id} not found")
