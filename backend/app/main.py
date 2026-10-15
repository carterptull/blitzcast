from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.routers import games, predictions, record, schedule, teams


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(
        title="Blitzcast API",
        description=(
            "Win probability predictions for NFL and college football, "
            "by Paymon Software."
        ),
        version="1.0.0",
        docs_url="/docs" if settings.api_docs else None,
        redoc_url="/redoc" if settings.api_docs else None,
        openapi_url="/openapi.json" if settings.api_docs else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def nosniff(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.include_router(teams.router)
    app.include_router(schedule.router)
    app.include_router(games.router)
    app.include_router(predictions.router)
    app.include_router(record.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app(get_settings())
