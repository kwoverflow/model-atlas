from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import ControlPlaneOverviewResponse, ModelComparisonRow, OverviewResponse
from app.services import analytics
from app.services.control_plane_overview import build_control_plane_overview

router = APIRouter()


@router.get("/overview", response_model=OverviewResponse)
def overview(db: Session = Depends(get_db)) -> OverviewResponse:
    return analytics.get_overview(db)


@router.get("/control-plane-overview", response_model=ControlPlaneOverviewResponse)
def control_plane_overview(db: Session = Depends(get_db)) -> ControlPlaneOverviewResponse:
    return build_control_plane_overview(db)


@router.get("/model-comparison", response_model=list[ModelComparisonRow])
def model_comparison(db: Session = Depends(get_db)) -> list[ModelComparisonRow]:
    return analytics.get_model_comparison(db)
