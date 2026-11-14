from fastapi import APIRouter, Depends, HTTPException
from ..auth import current_user_id

from ..schemas_insights import InsightsResponse

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("", response_model=InsightsResponse)
async def insights(user_id = Depends(current_user_id)) -> InsightsResponse:
    raise HTTPException(status_code=501, detail="Database analytics aggregation is not implemented")

