"""Private Richon backend: health checks and pending orders, no payments."""

import logging

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from auth_http import install_if_enabled
from db import DatabaseConfigurationError, check_database
from orders import router as orders_router

logger = logging.getLogger("richon.health")
app = FastAPI(
    title="Richon private backend",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    debug=False,
)
app.include_router(orders_router)
install_if_enabled(app)  # Default OFF; no provider login endpoint is exposed.


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    # The default validation response includes input values; never echo PII.
    return JSONResponse(
        status_code=422, content={"detail": "invalid_request"},
        headers={"Cache-Control": "no-store"},
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
