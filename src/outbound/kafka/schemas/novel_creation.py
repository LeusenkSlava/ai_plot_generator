from pydantic import BaseModel


class NovelCreateRequested(BaseModel):
    request_id: str
    prompt: str


class NovelCreated(BaseModel):
    request_id: str
    novel_id: str


class NovelCreationFailed(BaseModel):
    request_id: str
    reason: str
