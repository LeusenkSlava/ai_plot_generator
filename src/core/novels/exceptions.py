class NovelNotFoundError(Exception):
    def __init__(self, novel_id: int):
        self.novel_id = novel_id
        super().__init__(f"Novel {novel_id} not found")

class NovelGenerationError(Exception):
    """AI не смог сгенерировать описание."""