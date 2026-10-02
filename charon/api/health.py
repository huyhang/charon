from fastapi import APIRouter, Depends

from charon.api.deps import get_container
from charon.api.schemas import HealthView
from charon.container import Container

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health(container: Container = Depends(get_container)) -> HealthView:
    reachable = container.downloader.is_available()
    return HealthView(downloader="reachable" if reachable else "unreachable")
