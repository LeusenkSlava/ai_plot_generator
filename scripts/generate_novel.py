#!/usr/bin/env python3
"""Генерация новеллы целиком через My Choice API (без интерактивного чтения).

Скрипт делает ровно то, что делает клиентское приложение (Ren'Py «My Choice»),
но проходит новеллу до конца сам, реплика за репликой:

    1. POST /novels/          — создаёт задачу генерации новеллы по промпту;
    2. GET /generation-jobs/  — ждёт, пока новелла сгенерируется;
    3. GET /novels/{id}/next  — читает реплики по одной. Когда реплики сцены
       заканчиваются, сервис сам запускает генерацию следующей сцены; если
       сцена ещё не готова, `next` возвращает задачу, и скрипт ждёт её.

В итоге новелла оказывается полностью сгенерированной в БД, и её можно сразу
открыть в приложении без ожидания. Текст по желанию сохраняется в файл.

Примеры:
    python3 scripts/generate_novel.py "Новелла про то, как герой учится писать промпты"
    python3 scripts/generate_novel.py "Детектив в киберпанке" --universe-id 1 --out novel.txt
    python3 scripts/generate_novel.py "Романтика в поезде" --base-url http://my_choice.localhost

Зависимости — только стандартная библиотека Python.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://my_choice.localhost"
DEFAULT_JOB_TIMEOUT = 300.0   # секунд на одну задачу генерации
DEFAULT_POLL_INTERVAL = 2.5   # интервал опроса статуса задачи
DEFAULT_TOTAL_TIMEOUT = 1800.0  # общий лимит на весь прогон (30 минут)


class ApiError(RuntimeError):
    """Ошибка взаимодействия с API."""


class JobTimeout(RuntimeError):
    """Генерация заняла слишком много времени."""


def _http(method: str, url: str, payload: dict | None, timeout: float):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise ApiError(f"Сервис недоступен ({url}): {exc.reason}") from exc
    except TimeoutError as exc:
        raise ApiError(f"Сервис не ответил вовремя ({url})") from exc


def call_json(base_url: str, method: str, path: str, payload: dict | None = None, timeout: float = 30.0):
    status, raw = _http(method, base_url + path, payload, timeout)
    body = None
    if raw:
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = None
    return status, body


def _detail(body) -> str:
    if isinstance(body, dict):
        return str(body.get("detail") or "")
    return ""


def wait_job(base_url: str, job_id: int, timeout: float, poll: float) -> dict:
    """Опрашивает задачу генерации до done/failed. Возвращает задачу."""
    deadline = time.monotonic() + timeout
    while True:
        status, body = call_json(base_url, "GET", f"/generation-jobs/{job_id}")
        if status != 200:
            raise ApiError(
                f"Не удалось получить статус задачи {job_id}: HTTP {status} {_detail(body)}"
            )
        if body.get("status") in ("done", "failed"):
            return body
        if time.monotonic() >= deadline:
            raise JobTimeout(
                f"Задача {job_id} не завершилась за {timeout:.0f} секунд "
                f"(текущий статус: {body.get('status')})"
            )
        time.sleep(poll)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Сгенерировать новеллу целиком через My Choice API.",
    )
    parser.add_argument("prompt", nargs="+", help="Текст промпта, по которому создаётся новелла")
    parser.add_argument("--universe-id", type=int, default=None, help="ID вселенной Codex (необязательно)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Адрес My Choice API (по умолчанию {DEFAULT_BASE_URL})")
    parser.add_argument("--out", default=None, help="Сохранить текст новеллы в файл")
    parser.add_argument("--job-timeout", type=float, default=DEFAULT_JOB_TIMEOUT, help="Таймаут одной задачи генерации, сек")
    parser.add_argument("--total-timeout", type=float, default=DEFAULT_TOTAL_TIMEOUT, help="Общий лимит на весь прогон, сек")
    parser.add_argument("--poll", type=float, default=DEFAULT_POLL_INTERVAL, help="Интервал опроса задач, сек")
    parser.add_argument("--quiet", action="store_true", help="Не печатать реплики, только итог")
    args = parser.parse_args()

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        parser.error("Промпт не может быть пустым")

    base_url = args.base_url.rstrip("/")
    started = time.monotonic()

    # 1. Создать задачу генерации новеллы.
    payload = {"prompt": prompt}
    if args.universe_id is not None:
        payload["universe_id"] = args.universe_id

    print(f"Создаю новеллу: «{prompt}»", file=sys.stderr)
    status, body = call_json(base_url, "POST", "/novels/", payload)
    if status != 202:
        raise ApiError(f"Не удалось создать новеллу: HTTP {status} {_detail(body)}")

    job_id = body["id"]
    print(f"Задача генерации новеллы: {job_id} (status={body.get('status')})", file=sys.stderr)

    job = wait_job(base_url, job_id, args.job_timeout, args.poll)
    if job.get("status") == "failed":
        raise ApiError(f"Новелла не сгенерирована: {job.get('error') or 'неизвестная ошибка'}")

    novel_id = job.get("result_id")
    if novel_id is None:
        raise ApiError(f"Задача {job_id} завершена, но result_id пуст: {job}")

    # 2. Карточка новеллы — для заголовка.
    title = None
    status, novel = call_json(base_url, "GET", f"/novels/{novel_id}")
    if status == 200 and isinstance(novel, dict):
        title = novel.get("title")

    if title:
        print(f"\nНовелла #{novel_id}: {title}", file=sys.stderr)
    else:
        print(f"\nНовелла #{novel_id}", file=sys.stderr)

    # 3. Читаем до конца; при необходимости `next` сам запускает генерацию сцен.
    offset: int | None = None
    transcript: list[str] = []
    if title:
        transcript.append(f"НОВЕЛЛА: {title}\n")
        description = novel.get("public_description") if isinstance(novel, dict) else None
        if description:
            transcript.append(f"{description}\n")

    scene_count = 0
    line_count = 0
    current_scene_id: int | None = None

    def elapsed() -> float:
        return time.monotonic() - started

    while True:
        if elapsed() > args.total_timeout:
            raise ApiError(
                f"Превышено общее время генерации ({args.total_timeout:.0f} сек): "
                f"прочитано {line_count} реплик в {scene_count} сценах"
            )

        path = f"/novels/{novel_id}/next"
        if offset is not None:
            path += f"?offset={offset}"

        status, body = call_json(base_url, "GET", path)

        if status == 202:
            # Сцена ещё генерируется: ждём задачу и повторяем тот же запрос.
            scene_job = (body or {}).get("job") or {}
            if not isinstance(scene_job, dict) or "id" not in scene_job:
                raise ApiError(f"В ответе 202 нет задачи генерации сцены: {body!r}")
            print(f"  … сцена генерируется (задача {scene_job['id']})", file=sys.stderr)
            scene_job = wait_job(base_url, scene_job["id"], args.job_timeout, args.poll)
            if scene_job.get("status") == "failed":
                raise ApiError(f"Сцена не сгенерирована: {scene_job.get('error') or 'неизвестная ошибка'}")
            continue

        if status != 200:
            raise ApiError(f"Неожиданный ответ GET /novels/{novel_id}/next: HTTP {status} {_detail(body)}")

        if not isinstance(body, dict):
            raise ApiError(f"Неожиданный формат ответа: {body!r}")

        step_status = body.get("status")
        if step_status == "finished":
            break
        if step_status != "ok":
            raise ApiError(f"Неизвестный статус воспроизведения: {body!r}")

        step = body["step"]
        dialogue = step["dialogue"]
        scene = step["scene"]
        character = step.get("character") or {}

        if scene.get("id") != current_scene_id:
            current_scene_id = scene.get("id")
            scene_count += 1
            header = f"\n--- Сцена {scene.get('order')}: {scene.get('title') or ''} ---"
            transcript.append(header)
            if not args.quiet:
                print(header)

        speaker = character.get("name") or "…"
        text = dialogue.get("text") or ""
        if dialogue.get("is_thought"):
            line = f"* {speaker} (мысль): {text}"
        else:
            line = f"{speaker}: {text}"
        transcript.append(line)
        line_count += 1
        if not args.quiet:
            print(line)

        offset = dialogue.get("id")
        if offset is None:
            raise ApiError(f"В реплике нет id: {dialogue!r}")

    transcript.append("\n[конец новеллы]\n")
    print(f"\nГотово за {elapsed():.0f} сек: сцен — {scene_count}, реплик — {line_count}.", file=sys.stderr)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as file:
            file.write("\n".join(transcript) + "\n")
        print(f"Текст сохранён: {args.out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ApiError, JobTimeout) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nПрервано пользователем.", file=sys.stderr)
        raise SystemExit(130)
