from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    google_id: Optional[str] = Field(default=None, index=True, unique=True)
    refresh_token: Optional[str] = None
    access_token: Optional[str] = None
    token_expiry: Optional[datetime] = None
    is_party_leader: bool = Field(default=False)


class Group(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)
    name: str
    party_leader_id: int


class Membership(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    group_id: int = Field(foreign_key="group.id")


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id")
    title: str
    description: Optional[str] = None
    event_type: str = Field(default="booking")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    source: str = Field(default="gmail")
    metadata_json: Optional[str] = None
    source_id: Optional[str] = Field(default=None, index=True)
