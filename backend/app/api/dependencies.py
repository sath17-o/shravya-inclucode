from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.health import HealthService


def get_health_service(settings: Annotated[Settings, Depends(get_settings)]) -> HealthService:
    return HealthService(settings)
