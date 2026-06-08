import secrets


def generate_group_code(length: int = 6) -> str:
    token = secrets.token_urlsafe(length)
    return token[:length].upper()
