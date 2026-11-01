"""Переиспользуемые сервисы тестирования промптов (вне админки).

``DialoguePromptTester`` композирует уже готовые компоненты (``DialogueContextLoader``,
``DialoguePromptBuilder``, ``DeepSeekGenerator``) — сам промпт не строит и в DeepSeek
не ходит, ничего не пишет в БД и не шлёт аналитику.
"""
