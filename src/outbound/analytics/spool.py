"""Локальный outbox для событий аналитики на случай недоступности Kafka.

Единственный файл-подстраховка: пока брокер недоступен, события дописываются
сюда (по строке JSON на событие); когда брокер снова доступен, фоновый воркер
``AnalyticsSink`` дренирует файл и перезаписывает его только строками, которые
отправить не удалось. Успешно отправленные строки удаляются.
"""

import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class Spool:
    """Добавочный файл-очередь с атомарной перезаписью после дренажа."""

    def __init__(self, path: Path):
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def append(self, event: dict) -> None:
        """Дописать событие в outbox."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            logger.error("spool: не удалось записать %s: %s", self._path, exc)

    def read(self) -> list[dict]:
        """Прочитать все события из outbox (битые строки пропускаются)."""
        if not self._path.exists():
            return []
        events: list[dict] = []
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.error("spool: не удалось прочитать %s: %s", self._path, exc)
            return []
        for line in lines:
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.error("spool: битая строка в %s: %s", self._path, exc)
        return events

    def rewrite(self, events: list[dict]) -> None:
        """Атомарно перезаписать файл списком событий (пустой список удаляет файл)."""
        if not events:
            try:
                if self._path.exists():
                    self._path.unlink()
            except OSError as exc:
                logger.error("spool: не удалось удалить %s: %s", self._path, exc)
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for event in events:
                    f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
            os.replace(tmp, self._path)
        except OSError as exc:
            logger.error("spool: не удалось перезаписать %s: %s", self._path, exc)
            try:
                os.unlink(tmp)
            except OSError:
                pass
