from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.inbound.http.root_router import make_fastapi_root_router
from src.inbound.kafka.consumer import build_consumer
from src.inbound.kafka.handlers import build_topic_handlers
from src.inbound.kafka.tasks.consume_loop import consume_loop
from src.main.config.logging import setup_logging
from src.main.config.settings import settings
from src.main.setup.background_tasks import BackgroundTaskRunner
from src.outbound.ai.client import build_deepseek_client, close_deepseek_client
from src.outbound.codex.client import build_codex_client, close_codex_client
from src.outbound.database.session import engine
from src.outbound.kafka.producer import build_producer

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.openai_client = build_deepseek_client()
    app.state.codex_client = build_codex_client()

    producer = build_producer()
    await producer.start()

    consumer = build_consumer()
    await consumer.start()

    background_tasks = BackgroundTaskRunner()
    background_tasks.start_all(
        {
            "consume_loop": partial(
                consume_loop, consumer, build_topic_handlers(producer)
            ),
        }
    )

    yield

    await background_tasks.shutdown()
    await consumer.stop()
    await producer.stop()
    await close_deepseek_client()
    await close_codex_client()
    await engine.dispose()


app = FastAPI(
    title=settings.app.SERVICE_NAME,
    version="1.0.0",
    summary=f"OpenAPI schema for {settings.app.SERVICE_NAME}",
    root_path=settings.app.ROOT_PATH.rstrip("/"),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(make_fastapi_root_router(debug_mode=settings.app.DEBUG_MODE))
