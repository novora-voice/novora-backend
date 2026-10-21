import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from novora.api.auth import get_current_user
from novora.api.auth_utils import ConfigurationOrm, UserOrm, get_db


class ConfiguredAgentPayload(BaseModel):
    id: Optional[str] = None
    name: str = Field(min_length=1, max_length=120)
    provider: str
    agent_type: str = "Conversational Agent"
    configuration_status: str = "ready"
    agent_id_ref: Optional[str] = None
    system_prompt: Optional[str] = None
    tools: List[str] = Field(default_factory=list)
    execution_mode: str = "sandbox"
    created_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    recent_evaluation_id: Optional[str] = None
    recent_evaluation_status: Optional[str] = None


router = APIRouter(prefix="/api/v1/configured-agents", tags=["Configured Agents"])
KEY_PREFIX = "configured_agent:"


@router.get("", response_model=List[ConfiguredAgentPayload])
def list_configured_agents(db: Session = Depends(get_db), user: UserOrm = Depends(get_current_user)):
    rows = db.query(ConfigurationOrm).filter(
        ConfigurationOrm.user_id == user.id,
        ConfigurationOrm.key.startswith(KEY_PREFIX),
    ).all()
    return [ConfiguredAgentPayload.model_validate(json.loads(row.value)) for row in rows if row.value]


@router.post("", response_model=ConfiguredAgentPayload, status_code=status.HTTP_201_CREATED)
def create_configured_agent(payload: ConfiguredAgentPayload, db: Session = Depends(get_db), user: UserOrm = Depends(get_current_user)):
    data = payload.model_dump(mode="json", exclude={"id"})
    data["id"] = f"agent_{uuid.uuid4().hex[:12]}"
    data["created_at"] = payload.created_at.isoformat() if payload.created_at else datetime.now(timezone.utc).isoformat()
    row = ConfigurationOrm(user_id=user.id, key=KEY_PREFIX + data["id"], value=json.dumps(data))
    db.add(row)
    db.commit()
    return ConfiguredAgentPayload.model_validate(data)


@router.put("/{agent_id}", response_model=ConfiguredAgentPayload)
def update_configured_agent(agent_id: str, payload: ConfiguredAgentPayload, db: Session = Depends(get_db), user: UserOrm = Depends(get_current_user)):
    row = db.query(ConfigurationOrm).filter(
        ConfigurationOrm.user_id == user.id,
        ConfigurationOrm.key == KEY_PREFIX + agent_id,
    ).first()
    if not row or not row.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Configured agent not found.")
    previous: Dict[str, Any] = json.loads(row.value)
    data = payload.model_dump(mode="json", exclude={"id"})
    data["id"] = agent_id
    data["created_at"] = previous.get("created_at")
    row.value = json.dumps(data)
    db.commit()
    return ConfiguredAgentPayload.model_validate(data)
