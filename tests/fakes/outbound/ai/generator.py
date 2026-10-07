class FakeGeneratorNotConfigured(RuntimeError):
    """Тест забыл настроить FakeGenerator."""


class FakeGenerator:
    """Управляемый LLM: отдаёт заданные ответы/ошибки по очереди.

    Пример:
        generator.returns({"title": "T"})
        generator.raises(RuntimeError("LLM down"))
        generator.always_returns({"title": "default"})

        # цепочкой
        generator.returns(a).returns(b).raises(RuntimeError("boom"))
    """

    def __init__(self) -> None:
        self._responses: list[dict] = []
        self._errors: list[Exception] = []
        self._default: dict | None = None
        self.calls: list[list[dict]] = []
        self.think_flags: list[bool] = []
        self.efforts: list[str | None] = []

    # ---------- настройка ----------

    def returns(self, payload: dict) -> "FakeGenerator":
        self._responses.append(payload)
        return self

    def raises(self, error: Exception) -> "FakeGenerator":
        self._errors.append(error)
        return self

    def always_returns(self, payload: dict) -> "FakeGenerator":
        self._default = payload
        return self

    def fails_with(
        self, error_type: type[Exception], message: str = ""
    ) -> "FakeGenerator":
        return self.raises(error_type(message))

    # ---------- GeneratorProtocol ----------

    async def generate(
        self,
        prompt: list[dict],
        think: bool = True,
        reasoning_effort: str | None = None,
    ) -> dict:
        self.calls.append(prompt)
        self.think_flags.append(think)
        self.efforts.append(reasoning_effort)

        if self._errors:
            raise self._errors.pop(0)
        if self._responses:
            return self._responses.pop(0)
        if self._default is not None:
            return self._default

        raise FakeGeneratorNotConfigured(
            "FakeGenerator: no response configured. "
            "Call .returns(), .raises() or .always_returns() before use."
        )

    # ---------- ассерты и наблюдение ----------

    @property
    def last_prompt(self) -> list[dict]:
        assert self.calls, "FakeGenerator: generate() was never called"
        return self.calls[-1]

    @property
    def last_system_prompt(self) -> str:
        return self.last_prompt[0]["content"]

    @property
    def last_user_prompt(self) -> str:
        return self.last_prompt[1]["content"]

    @property
    def last_prompt_roles(self) -> list[str]:
        return [m["role"] for m in self.last_prompt]

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def called(self) -> bool:
        return bool(self.calls)

    @property
    def not_called(self) -> bool:
        return not self.calls

    def assert_system_contains(self, *fragments: str) -> None:
        system = self.last_system_prompt
        system_lower = system.lower()
        for fragment in fragments:
            assert (
                fragment.lower() in system_lower
            ), f"Expected {fragment!r} in system prompt, got:\n{system}"

    def assert_system_not_contains(self, *fragments: str) -> None:
        system = self.last_system_prompt
        system_lower = system.lower()
        for fragment in fragments:
            assert (
                fragment.lower() not in system_lower
            ), f"Did not expect {fragment!r} in system prompt, got:\n{system}"
