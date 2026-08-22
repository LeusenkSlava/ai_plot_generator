#!/bin/bash

# Применяем миграции
echo "Applying database migrations..."
alembic upgrade head

# Запускаем приложение
echo "Starting application..."
exec uvicorn src.main.run:app --host 0.0.0.0 --port 8000 --reload
