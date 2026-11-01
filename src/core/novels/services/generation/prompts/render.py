"""Рендер шаблонов промптов с плейсхолдерами ``{var}``.

Плейсхолдер — ``{``, сразу за которым идёт идентификатор ``[A-Za-z_][A-Za-z0-9_]*``,
и ``}``. Такое узкое правило намеренно: JSON-схемы внутри промптов (``{ "key": … }``)
не задеваются, потому что в них ``{`` всегда стоит перед кавычкой/переносом, а не
перед словом. Подставленные значения не сканируются повторно, поэтому ``{`` и ``}``
в данных пользователя/персонажей безопасны.
"""

import re

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class MissingPromptVariableError(KeyError):
    """В шаблоне встречается плейсхолдер, для которого не передали значение."""


def render_template(template: str, **variables: object) -> str:
    """Подставляет ``{var}`` в шаблон; отсутствующие переменные — ошибка."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise MissingPromptVariableError(
                f"Prompt template references undefined variable {name!r}"
            )
        return str(variables[name])

    return _PLACEHOLDER.sub(replace, template)
