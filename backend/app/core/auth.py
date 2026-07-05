from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def require_write_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = get_settings().api_write_token
    if not expected or x_admin_token == expected:
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Operacion sensible: falta X-Admin-Token valido.",
    )
