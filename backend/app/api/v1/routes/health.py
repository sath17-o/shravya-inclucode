from fastapi import APIRouter, Depends

from app.api.dependencies import get_health_service
from app.contracts.common import HealthPayload, SuccessResponse
from app.services.health import HealthService

router = APIRouter()


@router.get("/health", response_model=SuccessResponse[HealthPayload])
def health(service: HealthService = Depends(get_health_service)) -> SuccessResponse[HealthPayload]:
    return SuccessResponse(data=service.get_health())
