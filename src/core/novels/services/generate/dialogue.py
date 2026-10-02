import logging
from dataclasses import dataclass, field

from src.core.codex.models import Background, Emotion, Outfit, Sprite
from src.core.codex.services import CodexService
from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces import GeneratorProtocol
from src.core.novels.models import (
    Character,
    DialogueLine,
    Roadmap,
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


@dataclass
class _SpriteAssets:
    sprite: Sprite
    outfits: dict[str, Outfit] = field(default_factory=dict)
    emotions: dict[str, Emotion] = field(default_factory=dict)


@dataclass
class _Assets:
    """Ассеты из Codex, доступные для сцены: фоны вселенной и спрайты персонажей."""

    backgrounds: dict[str, Background] = field(default_factory=dict)
    # character.id -> sprite.slug -> ассеты спрайта
    sprites: dict[int, dict[str, _SpriteAssets]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.backgrounds or self.sprites)


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
        self, scene_id: int, previous_lines: list[DialogueLine] | None = None
    ) -> list[DialogueLine]:
        """Диалог сцены. previous_lines — последние реплики перед сценой, чтобы диалог продолжал их."""
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

        prompt = self.__create_prompt(
            scene, roadmap, characters, assets, previous_lines or []
        )
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
                **self.__pick_assets(item, character, assets),
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
                emotions = await self._codex_service.get_emotions(
                    character.codex_character_id
                )
                by_sprite: dict[str, _SpriteAssets] = {}
                for sprite in await self._codex_service.get_sprites(
                    character.codex_character_id
                ):
                    outfits = await self._codex_service.get_outfits(sprite.id)
                    by_sprite[sprite.slug] = _SpriteAssets(
                        sprite=sprite,
                        outfits={o.slug: o for o in outfits},
                        emotions={
                            e.slug: e for e in emotions if e.sprite_id == sprite.id
                        },
                    )
                assets.sprites[character.id] = by_sprite
        except Exception as e:
            raise GenerationError(f"Codex assets request failed: {e}") from e
        return assets

    @staticmethod
    def __pick_assets(item: dict, character: Character, assets: _Assets) -> dict:
        """Переводит выбранные LLM slug'и в asset_key Codex. Неизвестный slug -> None, а не падение."""
        picked = {
            "background_asset_key": None,
            "sprite_asset_key": None,
            "outfit_asset_key": None,
            "emotion_asset_key": None,
        }
        if not assets:
            return picked

        background = assets.backgrounds.get(item.get("background_slug") or "")
        picked["background_asset_key"] = background.asset_key if background else None

        sprite_assets = assets.sprites.get(character.id, {}).get(
            item.get("sprite_slug") or ""
        )
        if sprite_assets:
            picked["sprite_asset_key"] = sprite_assets.sprite.asset_key
            outfit = sprite_assets.outfits.get(item.get("outfit_slug") or "")
            emotion = sprite_assets.emotions.get(item.get("emotion_slug") or "")
            picked["outfit_asset_key"] = outfit.asset_key if outfit else None
            picked["emotion_asset_key"] = emotion.asset_key if emotion else None

        missing = [k for k, v in picked.items() if v is None]
        if missing:
            logger.warning(
                f"DialogueGenerator: unresolved assets {missing} for line {item!r}"
            )
        return picked

    @staticmethod
    def __assets_catalog(characters: list[Character], assets: _Assets) -> str:
        lines = ["Фоны (background_slug):"]
        lines += [f"- {b.slug}: {b.description}" for b in assets.backgrounds.values()]
        for character in characters:
            sprites = assets.sprites.get(character.id)
            if not sprites:
                continue
            lines.append(f"Спрайты персонажа {character.name}:")
            for slug, sa in sprites.items():
                lines.append(f"- sprite_slug {slug}: {sa.sprite.description}")
                lines.append(
                    f"  outfit_slug: {', '.join(f'{o.slug} ({o.name})' for o in sa.outfits.values()) or '-'}"
                )
                lines.append(
                    f"  emotion_slug: {', '.join(f'{e.slug} ({e.name})' for e in sa.emotions.values()) or '-'}"
                )
        return "\n".join(lines)

    def __create_prompt(
        self,
        scene: Scene,
        roadmap: Roadmap,
        characters: list[Character],
        assets: _Assets,
        previous_lines: list[DialogueLine],
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
        user_content = (
            f"Сцена: {scene.title}\n"
            f"Описание сцены: {scene.description}\n"
            f"Цель шага сюжета: {roadmap.goal}\n"
            f"Персонажи:\n{cast}"
        )
        if previous_lines:
            names = {character.id: character.name for character in characters}
            recap = "\n".join(
                f"{names.get(line.character_id, '?')}: {line.text}"
                for line in previous_lines
            )
            user_content += f"\n\nПоследние реплики предыдущей сцены (продолжи историю, не повторяя их):\n{recap}"
        if assets:
            system_prompt["content"] += (
                "\nДля визуала каждой реплики выбери ассеты ТОЛЬКО из каталога ниже, "
                "указывая slug точно как в каталоге, и добавь в объект реплики поля:\n"
                "- background_slug - фон, подходящий месту и времени сцены (обычно один на всю сцену, "
                "меняй только если действие переходит в другое место);\n"
                "- sprite_slug - спрайт говорящего персонажа;\n"
                "- outfit_slug - наряд из списка выбранного спрайта;\n"
                "- emotion_slug - эмоция из списка выбранного спрайта, соответствующая тексту реплики.\n"
                "Если подходящего ассета нет - ставь null."
            )
            user_content += (
                f"\n\nКаталог ассетов:\n{self.__assets_catalog(characters, assets)}"
            )
        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]
