import json
import re
from typing import Any, Dict, List
from openai import OpenAI, OpenAIError

from .config import settings

PROMPT = """
You are a reliable assistant that extracts structured event information from a travel or booking email.
Return exactly valid JSON and nothing else. The JSON must be an array of objects, even when only one event is found.
Each object must include the fields:
- title
- description
- event_type (flight, hotel, transportation, meeting, event, booking, other)
- start_time (ISO 8601 or empty string)
- end_time (ISO 8601 or empty string)
- location
- metadata (object with airline, flight_number, hotel_name, reservation_code, confirmation_number, etc.)

If no clear event data exists, return a single object with title set to "Unknown booking" and description set to the email summary.
"""


def _extract_json(text: str) -> List[Dict[str, Any]]:
    cleaned = text.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return [json.loads(match.group(0))]
        except json.JSONDecodeError:
            pass

    raise ValueError("Unable to parse JSON from OpenAI response")


def extract_events_from_message(subject: str, body: str) -> List[Dict[str, Any]]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required to extract events")

    prompt = f"""
{PROMPT}

Email subject: {subject}
Email body:
{body}
"""
    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You extract structured event and booking data from travel receipt emails."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=700,
        )
    except OpenAIError as exc:
        raise RuntimeError(f"OpenAI extraction failed: {exc}") from exc

    choice = response.choices[0]
    text = None
    if hasattr(choice, "message"):
        message = choice.message
        if isinstance(message, dict):
            text = message.get("content")
        else:
            text = getattr(message, "content", None)
    if text is None:
        text = getattr(choice, "text", None)
    if not text:
        raise ValueError("OpenAI response did not contain a valid message payload")
    events = _extract_json(text)
    normalized = []
    for item in events:
        normalized.append(
            {
                "title": item.get("title", "Booking event"),
                "description": item.get("description", ""),
                "event_type": item.get("event_type", "booking"),
                "start_time": item.get("start_time") or None,
                "end_time": item.get("end_time") or None,
                "location": item.get("location") or None,
                "metadata": item.get("metadata", {}),
            }
        )
    return normalized
