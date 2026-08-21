import hashlib
import os
import secrets
from pathlib import Path
from typing import Optional

MIN_TOKEN_LENGTH = 32


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _validate(token: str) -> str:
    token = token.strip()
    if len(token) < MIN_TOKEN_LENGTH:
        raise ValueError("JANUS_SCOUT_TOKEN_TOO_SHORT")
    return token


def default_token_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "JANUS" / "secrets" / "scout-local.token"
    return Path.home() / ".local" / "share" / "janus" / "secrets" / "scout-local.token"


def read_token_file(path: str) -> str:
    return _validate(Path(path).read_text(encoding="utf-8"))


def create_token_file(path: str) -> str:
    token_path = Path(path)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(token_path.parent, 0o700)
    except OSError:
        pass
    token = secrets.token_urlsafe(48)
    fd = os.open(str(token_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
    except Exception:
        try:
            token_path.unlink(missing_ok=True)
        finally:
            raise
    try:
        os.chmod(token_path, 0o600)
    except OSError:
        pass
    return token


def resolve_service_token(create_if_missing: bool = False) -> Optional[str]:
    env_token = os.environ.get("JANUS_SCOUT_TOKEN")
    if env_token:
        return _validate(env_token)

    token_file = os.environ.get("JANUS_SCOUT_TOKEN_FILE")
    path = Path(token_file) if token_file else default_token_path()
    if path.exists():
        return read_token_file(str(path))
    if create_if_missing:
        return create_token_file(str(path))
    return None
