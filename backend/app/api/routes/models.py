from fastapi import APIRouter, HTTPException, Depends
from typing import List
from pydantic import BaseModel

from app.core.auth import require_auth
from app.models.user import User
from app.services.multi_person_detector import multi_person_detector, _MODEL_DIR


router = APIRouter()

class ModelInfo(BaseModel):
    name: str
    size: int
    modified: float
    is_active: bool

class SetModelRequest(BaseModel):
    model_name: str

@router.get("/", response_model=List[ModelInfo])
async def list_models(current_user: User = Depends(require_auth)):
    """사용 가능한 AI 모델 목록 조회"""
    if not _MODEL_DIR.exists():
        return []
    
    models = []
    active_model = multi_person_detector.current_model
    
    for file in _MODEL_DIR.glob("*.pt"):
        models.append(ModelInfo(
            name=file.name,
            size=file.stat().st_size,
            modified=file.stat().st_mtime,
            is_active=(file.name == active_model)
        ))
    
    return sorted(models, key=lambda x: x.name)

@router.post("/active")
async def set_active_model(
    request: SetModelRequest,
    current_user: User = Depends(require_auth)
):
    """AI 모델 교체"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
        
    success = multi_person_detector.reload_model(request.model_name)
    if not success:
        raise HTTPException(status_code=400, detail="모델 교체 실패")
        
    return {"status": "success", "current_model": request.model_name}

