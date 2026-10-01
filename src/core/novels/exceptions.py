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
