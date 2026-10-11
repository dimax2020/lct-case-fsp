from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.assessment.router import router as assessment_router
from app.chat.router import router as chat_router
from app.company.router import router as company_router
from app.core.errors import AppError, app_error_handler, error_payload, validation_message
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.demo.router import router as demo_router
from app.hints.router import router as hints_router
from app.invitation.router import router as invitation_router
from app.need.router import router as need_router
from app.profile.router import router as profile_router
from app.psych.router import router as psych_router
from app.resume.router import router as resume_router
from app.taxonomy.router import router as taxonomy_router
from app.vacancy.router import router as vacancy_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="Карьера ФСП", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, app_error_handler)

    @app.exception_handler(RequestValidationError)
    async def on_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        response = JSONResponse(
            status_code=422,
            content=error_payload("validation_error", validation_message(exc.errors()), [dict(item) for item in exc.errors()]),
        )
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            response.headers["X-Request-Id"] = request_id
        return response

    @app.get("/api/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    for router in (
        profile_router,
        resume_router,
        hints_router,
        assessment_router,
        psych_router,
        company_router,
        need_router,
        invitation_router,
        vacancy_router,
        chat_router,
        taxonomy_router,
        demo_router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
