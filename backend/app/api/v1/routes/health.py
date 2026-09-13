from fastapi import APIRouter

router = APIRouter()


@router.get("/health", response_model=dict[str, str])
def health() -> dict[str, str]:
    return {"status": "ok"}
