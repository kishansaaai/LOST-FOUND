"""Translate database errors into HTTP responses.

SQLSTATEs LF001/LF002/LF003 are raised by our own triggers and procedures
(see backend/sql/002_triggers.sql) so the DB is the single source of rules."""
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

_MAP = {
    "LF001": 403, "LF002": 409, "LF003": 404,
    "23505": 409,   # unique_violation
    "23503": 409,   # foreign_key_violation
    "23514": 422,   # check_violation
    "22P02": 422,   # invalid_text_representation (bad enum)
    "22000": 422,
    "42501": 403,   # insufficient_privilege (incl. RLS)
}


def sqlstate_of(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


def message_of(exc: DBAPIError) -> str:
    diag = getattr(exc.orig, "diag", None)
    return (getattr(diag, "message_primary", None) or str(exc.orig)).strip()


async def db_error_handler(_: Request, exc: DBAPIError) -> JSONResponse:
    state = sqlstate_of(exc)
    status = _MAP.get(state or "", 500)
    detail = message_of(exc) if status != 500 else "internal database error"
    return JSONResponse({"detail": detail, "code": state}, status_code=status)
