from src.inbound.kafka.handlers.plot_generation import handle_novel_create_requested
from src.outbound.kafka.schemas.novel_creation import NovelCreateRequested
from src.outbound.kafka.topic import Topics

HANDLERS = {
    Topics.NOVEL_EVENTS_CREATE: (NovelCreateRequested, handle_novel_create_requested),
}
