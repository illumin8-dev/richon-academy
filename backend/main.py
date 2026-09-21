"""Richon private backend bootstrap: process and read-only DB checks only."""

import logging

from fastapi import FastAPI, HTTPException, Response

from db import DatabaseConfigurationError, check_database

logger = logging.getLogger("richon.health")
app = FastAPI(
    title="Richon backend bootstrap",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    debug=False,
)


@app.get("/health")
def health(response: Response) -> dict[str, str]:
    """No database access: suitable for process/startup checks."""
    response.headers["Cache-Control"] = "no-store"
    return {"status": "ok"}


@app.get("/health/db")
def database_health(response: Response) -> dict[str, str]:
    """Manual, IAM-protected check; never use as a recurring liveness probe."""
    response.headers["Cache-Control"] = "no-store"
    try:
        reachable = check_database()
    except DatabaseConfigurationError:
        # Do not log exception text, traceback, DSN, username or password.
        logger.warning("database_configuration_invalid")
        raise HTTPException(
            status_code=503,
            detail="database_configuration_invalid",
            headers={"Cache-Control": "no-store"},
        ) from None
    except Exception:
        # Driver exceptions can contain hostnames and credentials. Deliberately
        # report a fixed code only; inspect configuration privately to diagnose.
        logger.warning("database_unavailable")
        raise HTTPException(
            status_code=503,
            detail="database_unavailable",
            headers={"Cache-Control": "no-store"},
        ) from None
    if not reachable:
        raise HTTPException(
            status_code=503,
            detail="database_unavailable",
            headers={"Cache-Control": "no-store"},
        )
    return {"status": "ok", "database": "reachable"}
