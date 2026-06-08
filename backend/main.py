import csv
import io
import json
from typing import Optional
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from oauthlib.oauth2 import OAuth2Error
from sqlmodel import Session, select

from .config import settings
from .db import get_session, init_db
from .gmail_client import (
    build_gmail_service_for_user,
    exchange_code_for_credentials,
    get_google_authorization_url,
    GoogleOAuthStateError,
    load_booking_emails,
)
from .models import User, Group, Membership, Event
from .openai_client import extract_events_from_message
from .schemas import (
    AuthUrlResponse,
    GroupResponse,
    JoinGroupRequest,
    SyncRequest,
    SyncResponse,
    EventResponse,
)
from .utils import generate_group_code


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/auth/google/url", response_model=AuthUrlResponse)
def auth_google_url(party_name: Optional[str] = Query(None, description="Optional party name")):
    return AuthUrlResponse(authorization_url=get_google_authorization_url(party_name=party_name))


@app.get("/auth/google/callback")
@app.get("/google/auth/callback")
def auth_google_callback(code: str, state: Optional[str] = None, session: Session = Depends(get_session)):
    try:
        payload = exchange_code_for_credentials(code, state=state)
    except GoogleOAuthStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OAuth2Error as exc:
        detail = exc.description or exc.error or "Google authorization failed."
        raise HTTPException(status_code=400, detail=detail) from exc

    email = payload["email"]
    google_id = payload["google_id"]
    refresh_token = payload.get("refresh_token")
    access_token = payload.get("access_token")
    expiry = payload.get("expiry")

    user = session.exec(select(User).where(User.google_id == google_id)).first()
    if not user:
        user = User(
            email=email,
            google_id=google_id,
            refresh_token=refresh_token,
            access_token=access_token,
            token_expiry=expiry,
            is_party_leader=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    else:
        user.email = email
        user.refresh_token = refresh_token or user.refresh_token
        user.access_token = access_token or user.access_token
        user.token_expiry = expiry or user.token_expiry
        user.is_party_leader = True
        session.add(user)
        session.commit()

    group = session.exec(select(Group).where(Group.party_leader_id == user.id)).first()
    if not group:
        code = generate_group_code()
        party_name = payload.get("party_name") or "Party"
        group = Group(code=code, name=party_name, party_leader_id=user.id)
        session.add(group)
        session.commit()
        session.refresh(group)

    membership = session.exec(
        select(Membership).where(Membership.user_id == user.id, Membership.group_id == group.id)
    ).first()
    if not membership:
        membership = Membership(user_id=user.id, group_id=group.id)
        session.add(membership)
        session.commit()

    redirect_url = f"{settings.frontend_url}/?{urlencode({'group_code': group.code})}"
    return RedirectResponse(url=redirect_url)


@app.post("/groups/join")
def join_group(request: JoinGroupRequest, session: Session = Depends(get_session)):
    group = session.exec(select(Group).where(Group.code == request.code.upper())).first()
    if not group:
        raise HTTPException(status_code=404, detail="Party not found")

    if request.email:
        user = session.exec(select(User).where(User.email == request.email)).first()
        if not user:
            user = User(email=request.email)
            session.add(user)
            session.commit()
            session.refresh(user)

        membership = session.exec(
            select(Membership).where(Membership.user_id == user.id, Membership.group_id == group.id)
        ).first()
        if not membership:
            membership = Membership(user_id=user.id, group_id=group.id)
            session.add(membership)
            session.commit()

    return {"message": "joined", "group_code": group.code}


@app.get("/groups/{group_code}", response_model=GroupResponse)
def get_group(group_code: str, session: Session = Depends(get_session)):
    group = session.exec(select(Group).where(Group.code == group_code.upper())).first()
    if not group:
        raise HTTPException(status_code=404, detail="Party not found")

    party_leader = session.get(User, group.party_leader_id)
    if not party_leader:
        raise HTTPException(status_code=404, detail="Party leader not found")

    members = session.exec(select(Membership).where(Membership.group_id == group.id)).all()
    member_emails = []
    for membership in members:
        user = session.get(User, membership.user_id)
        if user and user.email:
            member_emails.append(user.email)

    events = session.exec(select(Event).where(Event.group_id == group.id)).all()
    event_responses = []
    for event in events:
        metadata = None
        if event.metadata_json:
            try:
                metadata = json.loads(event.metadata_json)
            except json.JSONDecodeError:
                metadata = {"raw": event.metadata_json}
        event_responses.append(
            EventResponse(
                id=event.id,
                title=event.title,
                description=event.description,
                event_type=event.event_type,
                start_time=event.start_time,
                end_time=event.end_time,
                location=event.location,
                source=event.source,
                metadata=metadata,
            )
        )

    return GroupResponse(
        code=group.code,
        name=group.name,
        party_leader_email=party_leader.email,
        members=member_emails,
        events=event_responses,
    )


@app.post("/sync", response_model=SyncResponse)
def sync_bookings(request: SyncRequest, session: Session = Depends(get_session)):
    group = session.exec(select(Group).where(Group.code == request.group_code.upper())).first()
    if not group:
        raise HTTPException(status_code=404, detail="Party not found")

    party_leader = session.get(User, group.party_leader_id)
    if not party_leader:
        raise HTTPException(status_code=404, detail="Party leader not found")
    if not party_leader.refresh_token:
        raise HTTPException(status_code=400, detail="Party leader Google account is not fully linked")

    service = build_gmail_service_for_user(party_leader)
    messages = load_booking_emails(service, query=request.label_query)
    synced_count = 0
    upserted_count = 0

    for message in messages:
        try:
            events = extract_events_from_message(message["subject"], message["body"])
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Booking extraction failed: {exc}") from exc
        synced_count += 1
        for event_payload in events:
            source_id = message["id"]
            existing = session.exec(
                select(Event).where(Event.group_id == group.id, Event.source_id == source_id)
            ).first()
            metadata_text = json.dumps(event_payload.get("metadata", {}))
            if existing:
                existing.title = event_payload["title"]
                existing.description = event_payload.get("description")
                existing.event_type = event_payload.get("event_type", "booking")
                existing.start_time = event_payload.get("start_time")
                existing.end_time = event_payload.get("end_time")
                existing.location = event_payload.get("location")
                existing.metadata_json = metadata_text
                session.add(existing)
            else:
                event = Event(
                    group_id=group.id,
                    title=event_payload["title"],
                    description=event_payload.get("description"),
                    event_type=event_payload.get("event_type", "booking"),
                    start_time=event_payload.get("start_time"),
                    end_time=event_payload.get("end_time"),
                    location=event_payload.get("location"),
                    source="gmail",
                    metadata_json=metadata_text,
                    source_id=source_id,
                )
                session.add(event)
            upserted_count += 1

    session.commit()
    return SyncResponse(
        synced_messages=synced_count,
        events_upserted=upserted_count,
        group_code=group.code,
    )


@app.get("/groups/{group_code}/csv")
def export_group_csv(group_code: str, session: Session = Depends(get_session)):
    group = session.exec(select(Group).where(Group.code == group_code.upper())).first()
    if not group:
        raise HTTPException(status_code=404, detail="Party not found")

    events = session.exec(select(Event).where(Event.group_id == group.id)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Title",
        "Description",
        "Event Type",
        "Start Time",
        "End Time",
        "Location",
        "Metadata",
    ])

    for event in events:
        writer.writerow([
            event.title,
            event.description or "",
            event.event_type,
            event.start_time.isoformat() if event.start_time else "",
            event.end_time.isoformat() if event.end_time else "",
            event.location or "",
            event.metadata_json or "",
        ])

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=syncup_{group.code}_events.csv"},
    )


@app.get("/")
def root():
    return {"message": "active"}
