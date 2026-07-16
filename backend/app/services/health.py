from app.contracts.common import HealthPayload
from app.core.config import Settings


class HealthService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_health(self) -> HealthPayload:
        return HealthPayload(
            environment=self._settings.environment,
            provider_mode=self._settings.provider_mode.value,
        )
