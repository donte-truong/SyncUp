from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List, Dict, Any


class AuthUrlResponse(BaseModel):
    authorization_url: str


class GoogleCallbackResponse(BaseModel):
    email: EmailStr
    google_id: Optional[str] = None
    is_party_leader: bool = False
    group_code: str
    group_name: str


class JoinGroupRequest(BaseModel):
    code: str
    email: Optional[EmailStr] = None


class SyncRequest(BaseModel):
    group_code: str
    label_query: Optional[str] = None


class EventResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    event_type: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    location: Optional[str]
    source: str
    metadata: Optional[Dict[str, Any]]


class GroupResponse(BaseModel):
    code: str
    name: str
    party_leader_email: EmailStr
    members: List[EmailStr]
    events: List[EventResponse]


class SyncResponse(BaseModel):
    synced_messages: int
    events_upserted: int
    group_code: str
