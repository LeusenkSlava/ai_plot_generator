import logging

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import (
    Character,
    DialogueLine,
    Scene,
)
from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generation.assets import (
    LineAssets,
    ResolvedAssets,
    SceneAssets,
    SceneAssetService,
    _short,
)
from src.core.novels.services.generation.generators.base import BaseGenerator
from src.core.novels.services.generation.prompts.cast import (
    find_protagonist,
    render_cast,
)

logger = logging.getLogger(__name__)

PREVIOUS_LINE_MAX_CHARS = 300


class DialogueGenerator(BaseGenerator):
    """Генерация диалога: сущности → ассеты → промпт → LLM → сохранение."""

    def __init__(
        self,
        novel_service: NovelService,
        scene_service: SceneService,
        roadmap_service: RoadmapService,
        character_service: CharacterService,
        dialogue_line_service: DialogueLineService,
        scene_assets: SceneAssetService,
        generator: GeneratorProtocol,
        reasoning_effort: str | None = None,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._scene_assets = scene_assets
        self._scene_service = scene_service
        self._roadmap_service = roadmap_service
        self._character_service = character_service
        self._dialogue_line_service = dialogue_line_service
        self._reasoning_effort = reasoning_effort

    async def generate(
        self,
        scene_id: int,
        previous_lines: list[DialogueLine] | None = None,
        story_context: str | None = None,
    ) -> list[DialogueLine]:
        """Генерация диалога"""
        scene = await self._scene_service.get(scene_id)
        if not scene:
            raise GenerationError(f"Scene with id {scene_id} not found")

        roadmap = await self._roadmap_service.get(scene.roadmap_id)
        if not roadmap:
            raise GenerationError(f"Roadmap with id {scene.roadmap_id} not found")

        characters, all_characters = await self._scene_cast(scene, roadmap.novel_id)
        if not characters:
            raise GenerationError(f"No characters found for novel {roadmap.novel_id}")

        characters_by_name = {character.name: character for character in characters}
        protagonist = find_protagonist(characters)

        novel = await self._novel_service.get(roadmap.novel_id)

        assets = await self._scene_assets.load_assets(
            novel.universe_id if novel else None, all_characters
        )
        last_outfits = await self._dialogue_line_service.last_outfit_per_character(
            roadmap.novel_id
        )
        current_outfits = self._scene_assets.current_outfits(
            characters, assets, last_outfits
        )

        prompt = self.__create_prompt(
            scene,
            characters,
            all_characters,
            protagonist,
            assets,
            previous_lines or [],
            story_context,
            current_outfits,
        )
        data = await self._generate(prompt, reasoning_effort=self._reasoning_effort)

        lines_data = data.get("dialogue_lines")
        if not lines_data:
            raise GenerationError("Generator returned no dialogue lines")

        # Фаза 1: запросы на подбор фона/спрайта/одежды/эмоции по тегам от LLM
        prepared: list[tuple[Character, dict, LineAssets]] = []
        for item in lines_data:
            character = characters_by_name.get(item["character_name"])
            if not character:
                raise GenerationError(
                    f"Generator referenced unknown character '{item['character_name']}'"
                )
            prepared.append(
                (
                    character,
                    item,
                    self._scene_assets.prepare_line(item, character, assets),
                )
            )

        # Фаза 2: подбираем фон/эмоцию/спрайт/одежду через Codex (параллельно)
        resolved = await self._scene_assets.match_assets(
            prepared, assets, novel.universe_id if novel else None
        )

        # Фаза 3: сохраняем реплики с итоговыми asset_key
        dialogue_lines = []
        last_index = len(lines_data) - 1
        for index, (character, item, _) in enumerate(prepared):
            assets_picked: ResolvedAssets = resolved[index]
            dialogue_line = DialogueLine(
                id=None,
                created_at=None,
                updated_at=None,
                novel_id=roadmap.novel_id,
                scene_id=scene.id,
                character_id=character.id,
                order=index + 1,
                text=item["text"],
                is_final_for_scene=index == last_index,
                is_thought=(
                    bool(item.get("is_thought", False))
                    if character.is_protagonist
                    else False
                ),
                background_asset_key=assets_picked.background_asset_key,
                sprite_asset_key=assets_picked.sprite_asset_key,
                outfit_asset_key=assets_picked.outfit_asset_key,
                emotion_asset_key=assets_picked.emotion_asset_key,
            )
            dialogue_line = await self._dialogue_line_service.add(dialogue_line)
            dialogue_lines.append(dialogue_line)

        return dialogue_lines

    async def _scene_cast(
        self, scene: Scene, novel_id: int
    ) -> tuple[list[Character], list[Character]]:
        """Персонажи, присутствующие в сцене, и весь каст новеллы.

        Список «кто в сцене» формирует SceneGenerator (scene.character_ids) по месту/времени
        шага. Если список пуст (старая сцена без списка), возвращаем весь каст — обратная
        совместимость с уже сгенерированными сценами. Весь каст нужен отдельно, чтобы
        подписывать имена в «последних репликах» даже для персонажей не из текущей сцены.
        """
        all_characters = await self._character_service.list_by_novel(novel_id) or []
        if not scene.character_ids:
            return all_characters, all_characters
        ids = set(scene.character_ids)
        return [c for c in all_characters if c.id in ids], all_characters

    def __create_prompt(
        self,
        scene: Scene,
        characters: list[Character],
        all_characters: list[Character],
        protagonist: Character | None,
        assets: SceneAssets,
        previous_lines: list[DialogueLine],
        story_context: str | None,
        current_outfits: str,
    ) -> list[dict]:
        # Полный каст в фиксированном порядке — стабильная голова промпта для кэша.
        cast = render_cast(all_characters)
        scene_participants = ", ".join(c.name for c in characters)

        system_prompt = {
            "role": "system",
            "content": (
                "Ты сценарист интерактивных визуальных новелл. "
                "На основе описания сцены и списка персонажей напиши диалог, который в ней происходит. "
                "Пиши реплики только за персонажей, перечисленных в блоке «Участники сцены»; "
                "остальные персонажи новеллы в этой сцене не появляются и не говорят. "
                "Количество реплик определи сам исходя из содержания сцены — обычно от 8 до 16, "
                "но не меньше 6. Не обрывай сцену на полуслове: доводи ключевой разговор сцены "
                "до логичной точки, а не обрезай его на чужой реплике-зацепке. "
                "Не заканчивай сцену мыслью-выводом или моралью, которая проговаривает уже показанное: "
                "финальная реплика сцены должна оставлять конкретную деталь, действие или реплику, "
                "а не интерпретацию; избегай оборотов «кажется», «может», «наверное», «это и называется». "
                "Кульминацию (выступление, признание, решающий поступок) не пересказывай итогом: "
                "показывай её по битам — хотя бы один кризисный момент внутри события и его преодоление, "
                "прежде чем оно завершится. "
                "История линейная: не предлагай игроку вариантов выбора.\n"
                "Для каждой реплики укажи:\n"
                "1. character_name - имя говорящего персонажа, точно как в списке.\n"
                "2. text - текст реплики.\n"
                "3. is_thought - boolean. True, если реплика главного героя — его внутренние мысли "
                "(не произносится вслух, отображается как внутренний монолог); для речи вслух и для "
                "остальных персонажей всегда false.\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
                """
                {
                  "dialogue_lines": [
                    {
                      "character_name": string,
                      "text": string,
                      "is_thought": boolean
                    }
                  ]
                }
                """
            ),
        }
        if protagonist:
            system_prompt["content"] += (
                f"\nГлавный герой — {protagonist.name}. История идёт от его лица, "
                "поэтому строй диалог вокруг его восприятия, целей и решений. "
                "У него нет спрайта и эмоций на экране: для его реплик не указывай спрайт, наряд и эмоции. "
                "Его реплики могут быть речью вслух (is_thought=false) или внутренними мыслями "
                "(is_thought=true) — используй внутренние мысли, чтобы передавать его переживания и мотивы."
            )
        # Сначала неизменное для новеллы (персонажи, каталог), потом меняющееся:
        # так работает кеш префикса у провайдера
        user_content = f"Персонажи новеллы:\n{cast}"
        if assets:
            system_prompt["content"] += (
                "\nДля визуала каждой реплики выбери ассеты ТОЛЬКО из каталога, "
                "указывая slug и теги точно как в каталоге, и добавь в объект реплики поля:\n"
                "- background_base_tag - ОДИН тег локации из списка локаций, подходящий месту сцены "
                "(обычно один на всю сцену, меняй только если действие переходит в другое место);\n"
                "- background_modifier_tags - список из 0 и более тегов-уточнений из списка уточнений "
                "(время суток, внутри/снаружи, свет, люди), соответствующих времени и обстановке сцены;\n"
                "- sprite_slug - спрайт говорящего персонажа;\n"
                "- outfit_tag - ОДИН тег стиля одежды из списка одежды говорящего;\n"
                "- emotion_base_tag - ОДИН главный тег эмоции говорящего из его базовых эмоций, "
                "соответствующий тексту реплики;\n"
                "- emotion_modifier_tags - список из 0 и более тегов-уточнений эмоции "
                "из модификаторов говорящего.\n"
                "Для реплик главного героя (без спрайта) ставь null для sprite_slug, outfit_tag, "
                "emotion_base_tag и пустой список [] для emotion_modifier_tags; "
                "фон (background_base_tag и background_modifier_tags) укажи как для остальных реплик.\n"
                "Если подходящего ассета нет - ставь null; для emotion_modifier_tags ставь пустой список [].\n"
                "Наряд персонажа не меняется между репликами и сценами: используй его текущий "
                "outfit_tag, пока по сюжету персонаж явно не переоделся."
            )
            user_content += f"\n\nКаталог ассетов:\n{self._scene_assets.assets_catalog(all_characters, assets)}"
        if story_context:
            user_content += (
                "\n\nИзложение истории на данный момент (не противоречь ему, "
                "персонажи одеты так, как в нём указано, пока по сюжету не переоденутся):\n"
                f"{story_context}"
            )
        if current_outfits:
            user_content += f"\n\nТекущие наряды персонажей:\n{current_outfits}"
        if previous_lines:
            names = {character.id: character.name for character in all_characters}
            recap = "\n".join(
                f"{names.get(line.character_id, '?')}"
                f"{' (мысли)' if line.is_thought else ''}: "
                f"{_short(line.text, PREVIOUS_LINE_MAX_CHARS)}"
                for line in previous_lines
            )
            user_content += f"\n\nПоследние реплики предыдущей сцены (продолжи историю, не повторяя их):\n{recap}"
        user_content += f"\n\nСцена: {scene.title}\nОписание сцены: {scene.description}"
        user_content += f"\nУчастники сцены: {scene_participants}"

        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]
