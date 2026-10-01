import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.inbound.http.root_router import make_fastapi_root_router
from src.inbound.kafka.consumer import build_consumer, consume_loop
from src.main.config.logging import setup_logging
from src.main.config.settings import settings
from src.outbound.ai.client import build_deepseek_client, close_deepseek_client
from src.outbound.codex.client import build_codex_client, close_codex_client
from src.outbound.database.session import engine

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.openai_client = build_deepseek_client()
    app.state.codex_client = build_codex_client()
    consumer = build_consumer()
    await consumer.start()
    consumer_task = asyncio.create_task(consume_loop(consumer))

    yield

    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await consumer.stop()
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
