import asyncio
import logging
from dataclasses import dataclass, field

from src.core.codex.exceptions import CodexUnavailableError
from src.core.codex.models import (
    Background,
    EmotionTags,
    Outfit,
    Sprite,
    Tag,
    TagType,
)
from src.core.codex.services import CodexService
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
from src.core.novels.services.generate.base import BaseGenerator

logger = logging.getLogger(__name__)

# Реплики прошлой сцены нужны только для стыка - длинные авторские вставки обрезаем
PREVIOUS_LINE_MAX_CHARS = 300
SPRITE_DESCRIPTION_MAX_CHARS = 100


def _short(text: str, limit: int = SPRITE_DESCRIPTION_MAX_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


@dataclass
class _SpriteAssets:
    sprite: Sprite
    outfits: dict[str, Outfit] = field(default_factory=dict)


@dataclass
class _Assets:
    """Ассеты из Codex, доступные для сцены: фоны вселенной и спрайты персонажей."""

    backgrounds: dict[str, Background] = field(default_factory=dict)
    # character.id -> sprite.slug -> ассеты спрайта
    sprites: dict[int, dict[str, _SpriteAssets]] = field(default_factory=dict)
    # character.id -> доступные эмоции-теги (база + модификаторы)
    emotion_tags: dict[int, EmotionTags] = field(default_factory=dict)
    # character.id -> доступные теги одежды (outfit_style)
    outfit_tags: dict[int, list[Tag]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.backgrounds or self.sprites)


@dataclass
class _LineAssets:
    """Подготовленные по реплике ассеты: фон и запросы подбора спрайта/одежды/эмоции."""

    background_asset_key: str | None = None
    # кандидат-спрайт, выбранный LLM; используется как подсказка для match_emotion
    sprite_id: int | None = None
    emotion_tags: list[str] | None = None
    outfit_tag: str | None = None


@dataclass
class _ResolvedAssets:
    """Итоговые asset_key реплики после подбора эмоции/спрайта/одежды."""

    background_asset_key: str | None = None
    sprite_asset_key: str | None = None
    outfit_asset_key: str | None = None
    emotion_asset_key: str | None = None


class DialogueGenerator(BaseGenerator):
    def __init__(
        self,
        novel_service: NovelService,
        scene_service: SceneService,
        roadmap_service: RoadmapService,
        character_service: CharacterService,
        dialogue_line_service: DialogueLineService,
        codex_service: CodexService,
        generator: GeneratorProtocol,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._codex_service = codex_service
        self._scene_service = scene_service
        self._roadmap_service = roadmap_service
        self._character_service = character_service
        self._dialogue_line_service = dialogue_line_service

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

        characters = await self._character_service.list_by_novel(roadmap.novel_id)
        if not characters:
            raise GenerationError(f"No characters found for novel {roadmap.novel_id}")
        characters_by_name = {character.name: character for character in characters}

        novel = await self._novel_service.get(roadmap.novel_id)
        assets = await self.__load_assets(
            novel.universe_id if novel else None, characters
        )

        last_outfits = await self._dialogue_line_service.last_outfit_per_character(
            roadmap.novel_id
        )
        current_outfits = self.__current_outfits(characters, assets, last_outfits)

        prompt = self.__create_prompt(
            scene,
            characters,
            assets,
            previous_lines or [],
            story_context,
            current_outfits,
        )
        data = await self._generate(prompt)

        lines_data = data.get("dialogue_lines")
        if not lines_data:
            raise GenerationError("Generator returned no dialogue lines")

        # Фаза 1: фон (статически) и запросы на подбор спрайта/одежды/эмоции по тегам
        prepared: list[tuple[Character, dict, _LineAssets]] = []
        for item in lines_data:
            character = characters_by_name.get(item["character_name"])
            if not character:
                raise GenerationError(
                    f"Generator referenced unknown character '{item['character_name']}'"
                )
            prepared.append(
                (character, item, self.__prepare_line(item, character, assets))
            )

        # Фаза 2: подбираем эмоцию/спрайт/одежду через Codex (параллельно)
        resolved = await self.__match_assets(prepared, assets)

        # Фаза 3: сохраняем реплики с итоговыми asset_key
        dialogue_lines = []
        last_index = len(lines_data) - 1
        for index, (character, item, _) in enumerate(prepared):
            assets_picked = resolved[index]
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
                background_asset_key=assets_picked.background_asset_key,
                sprite_asset_key=assets_picked.sprite_asset_key,
                outfit_asset_key=assets_picked.outfit_asset_key,
                emotion_asset_key=assets_picked.emotion_asset_key,
            )
            dialogue_line = await self._dialogue_line_service.add(dialogue_line)
            dialogue_lines.append(dialogue_line)

        return dialogue_lines

    async def __load_assets(
        self, universe_id: int | None, characters: list[Character]
    ) -> _Assets:
        assets = _Assets()
        # Без вселенной в Codex не ходим
        if universe_id is None:
            return assets
        try:
            assets.backgrounds = {
                b.slug: b
                for b in await self._codex_service.get_backgrounds(universe_id)
            }
            for character in characters:
                if character.codex_character_id is None:
                    continue
                assets.emotion_tags[character.id] = (
                    await self._codex_service.get_emotion_tags(
                        character.codex_character_id
                    )
                )
                assets.outfit_tags[character.id] = (
                    await self._codex_service.get_outfit_tags(
                        character.codex_character_id
                    )
                )
                by_sprite: dict[str, _SpriteAssets] = {}
                for sprite in await self._codex_service.get_sprites(
                    character.codex_character_id
                ):
                    outfits = await self._codex_service.get_outfits(sprite.id)
                    by_sprite[sprite.slug] = _SpriteAssets(
                        sprite=sprite,
                        outfits={o.slug: o for o in outfits},
                    )
                assets.sprites[character.id] = by_sprite
        except Exception as e:
            raise GenerationError(f"Codex assets request failed: {e}") from e
        return assets

    @staticmethod
    def __prepare_line(
        item: dict, character: Character, assets: _Assets
    ) -> _LineAssets:
        """Переводит выбранные LLM slug'и/теги в запросы подбора ассетов Codex."""
        line = _LineAssets()
        if not assets:
            return line

        background = assets.backgrounds.get(item.get("background_slug") or "")
        line.background_asset_key = background.asset_key if background else None
        if line.background_asset_key is None and item.get("background_slug"):
            logger.warning(
                f"DialogueGenerator: unresolved background_slug for line {item!r}"
            )

        sprite_assets = assets.sprites.get(character.id, {}).get(
            item.get("sprite_slug") or ""
        )
        if sprite_assets:
            line.sprite_id = sprite_assets.sprite.id
        elif item.get("sprite_slug"):
            logger.warning(
                f"DialogueGenerator: unresolved sprite_slug for line {item!r}"
            )

        base_tag = item.get("emotion_base_tag")
        if base_tag:
            modifier_tags = item.get("emotion_modifier_tags") or []
            line.emotion_tags = [base_tag, *modifier_tags]

        line.outfit_tag = item.get("outfit_tag")

        return line

    async def __match_assets(
        self, prepared: list[tuple[Character, dict, _LineAssets]], assets: _Assets
    ) -> list[_ResolvedAssets]:
        """Подбирает по тегам эмоцию и одежду; финальный спрайт берёт из эмоции."""

        async def resolve(character: Character, line: _LineAssets) -> _ResolvedAssets:
            result = _ResolvedAssets(background_asset_key=line.background_asset_key)
            codex_id = character.codex_character_id

            # 1. Эмоция. match_emotion может вернуть эмоцию на другом спрайте,
            #    поэтому спрайт берём из результата, а не из выбора LLM.
            emotion = None
            if codex_id is not None and line.emotion_tags:
                try:
                    emotion = await self._codex_service.match_emotion(
                        codex_id, line.emotion_tags, sprite_id=line.sprite_id
                    )
                except CodexUnavailableError as e:
                    logger.warning(
                        f"DialogueGenerator: emotion match failed for "
                        f"{character.name} tags={line.emotion_tags}: {e}"
                    )
                if emotion is None:
                    logger.warning(
                        f"DialogueGenerator: no emotion matched for "
                        f"{character.name} tags={line.emotion_tags}"
                    )

            # 2. Финальный спрайт: из подобранной эмоции, иначе — выбор LLM.
            final_sprite_id = emotion.sprite_id if emotion else line.sprite_id
            sprite_assets = self.__sprite_assets_by_id(
                character.id, final_sprite_id, assets
            )
            if sprite_assets:
                result.sprite_asset_key = sprite_assets.sprite.asset_key

            # 3. Одежда подбирается на финальном спрайте по одному тегу-стилю.
            if final_sprite_id is not None and line.outfit_tag:
                try:
                    outfit = await self._codex_service.match_outfit(
                        final_sprite_id, line.outfit_tag
                    )
                except CodexUnavailableError as e:
                    logger.warning(
                        f"DialogueGenerator: outfit match failed for "
                        f"{character.name} tag={line.outfit_tag} "
                        f"sprite={final_sprite_id}: {e}"
                    )
                    outfit = None
                if outfit:
                    result.outfit_asset_key = outfit.asset_key
                else:
                    logger.warning(
                        f"DialogueGenerator: no outfit matched for "
                        f"{character.name} tag={line.outfit_tag} "
                        f"sprite={final_sprite_id}"
                    )

            # 4. Эмоция.
            if emotion:
                result.emotion_asset_key = emotion.asset_key

            return result

        return await asyncio.gather(
            *(resolve(character, line) for character, _, line in prepared)
        )

    @staticmethod
    def __sprite_assets_by_id(
        character_id: int, sprite_id: int | None, assets: _Assets
    ) -> _SpriteAssets | None:
        if sprite_id is None:
            return None
        for sa in assets.sprites.get(character_id, {}).values():
            if sa.sprite.id == sprite_id:
                return sa
        return None

    @staticmethod
    def __current_outfits(
        characters: list[Character], assets: _Assets, last_outfits: dict[int, str]
    ) -> str:
        """Резолв последнего наряда каждого персонажа: asset_key -> тег одежды."""
        lines: list[str] = []

        for c in characters:
            asset_key = last_outfits.get(c.id)
            if not asset_key:
                continue
            for sa in assets.sprites.get(c.id, {}).values():
                for outfit in sa.outfits.values():
                    if outfit.asset_key == asset_key:
                        tag = next(
                            (
                                t.slug
                                for t in outfit.tags
                                if t.type == TagType.OUTFIT_STYLE
                            ),
                            None,
                        )
                        if tag:
                            lines.append(
                                f"- {c.name}: outfit_tag {tag} ({outfit.name})"
                            )
                        break
        return "\n".join(lines)

    @staticmethod
    def __assets_catalog(characters: list[Character], assets: _Assets) -> str:
        lines = ["Фоны (background_slug):"]
        lines += [f"- {b.slug}: {b.description}" for b in assets.backgrounds.values()]
        for character in characters:
            sprites = assets.sprites.get(character.id)
            if not sprites:
                continue
            lines.append(f"Спрайты (sprite_slug) персонажа {character.name}:")
            for slug, sa in sprites.items():
                lines.append(f"- {slug}: {_short(sa.sprite.description)}")
            tags = assets.emotion_tags.get(character.id)
            if tags:
                base = ", ".join(f"{t.slug}={t.name}" for t in tags.base) or "-"
                modifiers = (
                    ", ".join(f"{t.slug}={t.name}" for t in tags.modifiers) or "-"
                )
                lines.append(f"Эмоции персонажа {character.name}:")
                lines.append(f"  базовые (emotion_base_tag): {base}")
                lines.append(f"  модификаторы (emotion_modifier_tags): {modifiers}")
            outfit_tags = assets.outfit_tags.get(character.id)
            if outfit_tags:
                styles = (
                    ", ".join(f"{t.slug}={t.name}" for t in outfit_tags) or "-"
                )
                lines.append(
                    f"Одежда персонажа {character.name} (outfit_tag): {styles}"
                )
        return "\n".join(lines)

    def __create_prompt(
        self,
        scene: Scene,
        characters: list[Character],
        assets: _Assets,
        previous_lines: list[DialogueLine],
        story_context: str | None,
        current_outfits: str,
    ) -> list[dict]:
        cast = "\n".join(
            f"- {character.name} ({character.role}): {character.voice_notes}"
            for character in characters
        )

        system_prompt = {
            "role": "system",
            "content": (
                "Ты сценарист интерактивных визуальных новелл. "
                "На основе описания сцены и списка персонажей напиши диалог, который в ней происходит. "
                "Используй только персонажей из списка, ссылаясь на них по имени точно как в списке. "
                "Количество реплик определи сам исходя из содержания сцены — обычно от 4 до 12. "
                "История линейная: не предлагай игроку вариантов выбора.\n"
                "Для каждой реплики укажи:\n"
                "1. character_name - имя говорящего персонажа, точно как в списке.\n"
                "2. text - текст реплики.\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
                """
                {
                  "dialogue_lines": [
                    {
                      "character_name": string,
                      "text": string
                    }
                  ]
                }
                """
            ),
        }
        # Сначала неизменное для новеллы (персонажи, каталог), потом меняющееся:
        # так работает кеш префикса у провайдера
        user_content = f"Персонажи:\n{cast}"
        if assets:
            system_prompt["content"] += (
                "\nДля визуала каждой реплики выбери ассеты ТОЛЬКО из каталога, "
                "указывая slug точно как в каталоге, и добавь в объект реплики поля:\n"
                "- background_slug - фон, подходящий месту и времени сцены (обычно один на всю сцену, "
                "меняй только если действие переходит в другое место);\n"
                "- sprite_slug - спрайт говорящего персонажа;\n"
                "- outfit_tag - ОДИН тег стиля одежды из списка одежды говорящего;\n"
                "- emotion_base_tag - ОДИН главный тег эмоции говорящего из его базовых эмоций, "
                "соответствующий тексту реплики;\n"
                "- emotion_modifier_tags - список из 0 и более тегов-уточнений эмоции "
                "из модификаторов говорящего.\n"
                "Если подходящего ассета нет - ставь null; для emotion_modifier_tags ставь пустой список [].\n"
                "Наряд персонажа не меняется между репликами и сценами: используй его текущий "
                "outfit_tag, пока по сюжету персонаж явно не переоделся."
            )
            user_content += (
                f"\n\nКаталог ассетов:\n{self.__assets_catalog(characters, assets)}"
            )
        if story_context:
            user_content += (
                "\n\nИзложение истории на данный момент (не противоречь ему, "
                "персонажи одеты так, как в нём указано, пока по сюжету не переоденутся):\n"
                f"{story_context}"
            )
        if current_outfits:
            user_content += f"\n\nТекущие наряды персонажей:\n{current_outfits}"
        if previous_lines:
            names = {character.id: character.name for character in characters}
            recap = "\n".join(
                f"{names.get(line.character_id, '?')}: {_short(line.text, PREVIOUS_LINE_MAX_CHARS)}"
                for line in previous_lines
            )
            user_content += f"\n\nПоследние реплики предыдущей сцены (продолжи историю, не повторяя их):\n{recap}"
        user_content += f"\n\nСцена: {scene.title}\nОписание сцены: {scene.description}"

        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]
