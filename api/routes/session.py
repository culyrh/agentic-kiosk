# api/routes/session.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.sqlite import create_session, get_session, update_session

router = APIRouter(prefix="/session", tags=["session"])

class SessionUpdateRequest(BaseModel):
    current_state: str = ""
    last_recommended: str = ""

# 세션 생성
@router.post("/{session_id}")
def init_session(session_id: str):
    create_session(session_id)
    return {"session_id": session_id, "message": "세션이 생성됐습니다."}

# 세션 조회
@router.get("/{session_id}")
def get_session_info(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return session

# 세션 업데이트
@router.put("/{session_id}")
def update_session_info(session_id: str, req: SessionUpdateRequest):
    update_session(session_id, req.current_state, req.last_recommended)
    return {"message": "세션이 업데이트됐습니다."}