class NovelNotFoundError(Exception):
    def __init__(self, novel_id: int):
        self.novel_id = novel_id
        super().__init__(f"Novel {novel_id} not found")


class GenerationError(Exception):
    """AI не смог сгенерировать описание."""


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

    def __init__(self, novel_id: int, scene_order: int, next_scene_order: int):
        self.novel_id = novel_id
        self.scene_order = scene_order
        self.next_scene_order = next_scene_order
        super().__init__(
            f"Scene {scene_order} of novel {novel_id} cannot be generated: "
            f"previous scene {scene_order - 1} is not generated yet "
            f"(next scene to generate is {next_scene_order})"
        )
