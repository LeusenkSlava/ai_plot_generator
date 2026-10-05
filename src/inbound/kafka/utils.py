import json


def extract_job_id(raw: bytes) -> int | None:
    """job_id из невалидного сообщения - чтобы всё равно ответить failed."""
    try:
        return int(json.loads(raw).get("job_id"))
    except ValueError, TypeError, AttributeError:
        return None
