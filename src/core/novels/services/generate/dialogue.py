import logging

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces import GeneratorProtocol
from src.core.novels.models import Character, DialogueAction, DialogueLine, Roadmap, Scene
from src.core.novels.services.crud import (
    CharacterService,
    DialogueActionService,
    DialogueLineService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generate.base import BaseGenerator

logger = logging.getLogger(__name__)


class DialogueGenerator(BaseGenerator):
    def __init__(
        self,
        scene_service: SceneService,
        roadmap_service: RoadmapService,
        character_service: CharacterService,
        dialogue_line_service: DialogueLineService,
        dialogue_action_service: DialogueActionService,
        generator: GeneratorProtocol,
    ):
        super().__init__(generator)
        self._scene_service = scene_service
        self._roadmap_service = roadmap_service
        self._character_service = character_service
        self._dialogue_line_service = dialogue_line_service
        self._dialogue_action_service = dialogue_action_service

    async def generate(self, scene_id: int) -> list[DialogueLine]:
        scene = await self._scene_service.get(scene_id)
        if not scene:
            raise GenerationError(f"Scene with id {scene_id} not found")

        roadmap = await self._roadmap_service.get(scene.roadmap_id)
        if not roadmap:
            raise GenerationError(f"Roadmap with id {scene.roadmap_id} not found")

        characters = await self._character_service.list_by_novel(roadmap.novel_id)
        if not characters:
            raise GenerationError(f"No characters found for novel {roadmap.novel_id}")
        characters_by_name = {character.name: character for character in characters}

        prompt = self.__create_prompt(scene, roadmap, characters)
        data = await self._generate(prompt)

        lines_data = data.get("dialogue_lines")
        if not lines_data:
            raise GenerationError("Generator returned no dialogue lines")

        dialogue_lines = []
        last_index = len(lines_data) - 1
        for index, item in enumerate(lines_data):
            character = characters_by_name.get(item["character_name"])
            if not character:
                raise GenerationError(
                    f"Generator referenced unknown character '{item['character_name']}'"
                )

            is_final = index == last_index and roadmap.target_choice

            dialogue_line = DialogueLine(
                id=None,
                created_at=None,
                updated_at=None,
                novel_id=roadmap.novel_id,
                scene_id=scene.id,
                character_id=character.id,
                order=index + 1,
                text=item["text"],
                is_final_for_roadmap=is_final,
            )
            dialogue_line = await self._dialogue_line_service.add(dialogue_line)

            if is_final:
                for action_index, action_item in enumerate(item.get("actions") or []):
                    action = DialogueAction(
                        id=None,
                        created_at=None,
                        updated_at=None,
                        dialogue_line_id=dialogue_line.id,
                        order=action_index + 1,
                        text=action_item["text"],
                        next_roadmap_id=None,
                    )
                    await self._dialogue_action_service.add(action)

            dialogue_lines.append(dialogue_line)

        return dialogue_lines

    def __create_prompt(
        self, scene: Scene, roadmap: Roadmap, characters: list[Character]
    ) -> list[dict]:
        cast = "\n".join(
            f"- {character.name} ({character.role}): {character.voice_notes}"
            for character in characters
        )

        choice_instruction = (
            (
                "Эта сцена заканчивается развилкой сюжета. "
                "Последняя реплика должна подвести игрока к выбору, а в поле actions "
                "укажи 2-3 варианта выбора (только их текст), отражающих то, что поставлено на карту: "
                f"{roadmap.choice_stakes or roadmap.goal}."
            )
            if roadmap.target_choice
            else "У этой сцены нет развилки, поле actions оставляй пустым у каждой реплики."
        )

        system_prompt = {
            "role": "system",
            "content": (
                "Ты сценарист интерактивных визуальных новелл. "
                "На основе описания сцены и списка персонажей напиши диалог, который в ней происходит. "
                "Используй только персонажей из списка, ссылаясь на них по имени точно как в списке. "
                "Количество реплик определи сам исходя из содержания сцены — обычно от 4 до 12. "
                f"{choice_instruction}\n"
                "Для каждой реплики укажи:\n"
                "1. character_name - имя говорящего персонажа, точно как в списке.\n"
                "2. text - текст реплики.\n"
                "3. actions - список вариантов выбора (только для последней реплики, если есть развилка), "
                "каждый вариант - объект с полем text.\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
                """
                {
                  "dialogue_lines": [
                    {
                      "character_name": string,
                      "text": string,
                      "actions": [ { "text": string } ]
                    }
                  ]
                }
                """
            ),
        }
        user_prompt = {
            "role": "user",
            "content": (
                f"Сцена: {scene.title}\n"
                f"Описание сцены: {scene.description}\n"
                f"Цель шага сюжета: {roadmap.goal}\n"
                f"Персонажи:\n{cast}"
            ),
        }
        return [system_prompt, user_prompt]
