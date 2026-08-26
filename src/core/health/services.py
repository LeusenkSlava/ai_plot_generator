from dataclasses import dataclass

from src.core.health.interfaces import HealthCheckerProtocol


@dataclass
class ComponentResult:
    name: str
    ok: bool
    details: str | None = None

@dataclass
class HealthResult:
    healthy: bool
    components: list[ComponentResult]

class HealthService:
    async def check(self, checkers: dict[str, "HealthCheckerProtocol"]) -> HealthResult:
        results = []
        for name, checker in checkers.items():
            ok, details = await checker()
            results.append(ComponentResult(name=name, ok=ok, details=details))

        return HealthResult(
            healthy=all(r.ok for r in results),
            components=results,
        )