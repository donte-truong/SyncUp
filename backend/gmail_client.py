import base64
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from google_auth_oauthlib.flow import Flow
from google.oauth2 import credentials as google_credentials
from google.oauth2 import id_token
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from .config import settings
from .models import User

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
]
AUTH_STATE_TTL = timedelta(minutes=10)


class GoogleOAuthStateError(ValueError):
    pass


@dataclass
class PendingGoogleAuth:
    code_verifier: Optional[str]
    party_name: Optional[str]
    expires_at: datetime


_pending_google_auth: Dict[str, PendingGoogleAuth] = {}


def get_client_config() -> dict:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


def _prune_expired_auth_states(now: Optional[datetime] = None) -> None:
    now = now or datetime.now(timezone.utc)
    for state, pending_auth in list(_pending_google_auth.items()):
        if pending_auth.expires_at <= now:
            _pending_google_auth.pop(state, None)


def _build_flow(code_verifier: Optional[str] = None) -> Flow:
    flow = Flow.from_client_config(
        get_client_config(), scopes=SCOPES, redirect_uri=settings.google_redirect_uri
    )
    if code_verifier:
        flow.autogenerate_code_verifier = False
        flow.code_verifier = code_verifier
    return flow


def get_google_authorization_url(party_name: Optional[str] = None) -> str:
    _prune_expired_auth_states()
    state = secrets.token_urlsafe(32)
    flow = _build_flow()
    auth_url, _state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    _pending_google_auth[_state] = PendingGoogleAuth(
        code_verifier=getattr(flow, "code_verifier", None),
        party_name=party_name,
        expires_at=datetime.now(timezone.utc) + AUTH_STATE_TTL,
    )
    return auth_url


def exchange_code_for_credentials(code: str, state: Optional[str] = None) -> Dict[str, object]:
    _prune_expired_auth_states()
    pending_auth = _pending_google_auth.pop(state, None) if state else None
    if not pending_auth:
        raise GoogleOAuthStateError("Google sign-in expired. Please connect Gmail again.")

    flow = _build_flow(code_verifier=pending_auth.code_verifier)
    flow.fetch_token(code=code)
    creds = flow.credentials
    id_info = id_token.verify_oauth2_token(
        creds.id_token, Request(), settings.google_client_id
    )
    return {
        "email": id_info.get("email"),
        "google_id": id_info.get("sub"),
        "refresh_token": creds.refresh_token,
        "access_token": creds.token,
        "expiry": creds.expiry,
        "party_name": pending_auth.party_name,
    }


def build_gmail_service_for_user(user: User):
    creds = google_credentials.Credentials(
        token=user.access_token,
        refresh_token=user.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
        expiry=user.token_expiry,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def list_booking_message_ids(service, query: Optional[str] = None, max_results: int = 50) -> List[str]:
    query = query or settings.gmail_sync_query
    response = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = response.get("messages", [])
    return [item["id"] for item in messages if "id" in item]


def decode_part_body(data: str) -> str:
    payload = base64.urlsafe_b64decode(data.encode("utf-8"))
    return payload.decode("utf-8", errors="ignore")


def extract_message_text(message: Dict) -> str:
    payload = message.get("payload", {})
    parts = payload.get("parts") or []
    fragments = []

    def walk_part(part):
        mime_type = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if data and mime_type in ["text/plain", "text/html"]:
            fragments.append(decode_part_body(data))
        for subpart in part.get("parts", []) or []:
            walk_part(subpart)

    walk_part(payload)
    if not fragments:
        if payload.get("body", {}).get("data"):
            fragments.append(decode_part_body(payload["body"]["data"]))
    return "\n".join(fragments).strip()


def fetch_message(service, message_id: str) -> Dict:
    return service.users().messages().get(userId="me", id=message_id, format="full").execute()


def load_booking_emails(service, query: Optional[str] = None):
    message_ids = list_booking_message_ids(service, query)
    messages = []
    for message_id in message_ids:
        record = fetch_message(service, message_id)
        body = extract_message_text(record)
        headers = {h["name"]: h["value"] for h in record.get("payload", {}).get("headers", [])}
        messages.append(
            {
                "id": message_id,
                "snippet": record.get("snippet", ""),
                "subject": headers.get("Subject", "Booking"),
                "from": headers.get("From", ""),
                "body": body,
            }
        )
    return messages
