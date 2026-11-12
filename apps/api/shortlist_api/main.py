from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.requests import Request

from shortlist_api import privacy
from shortlist_api.config import get_settings
from shortlist_api.db import DbCheck, check_db
from shortlist_api.routes import profile, recommend
from shortlist_ml.embeddings.encoder import MissingMLDependencies

privacy.install()
app = FastAPI(title="Shortlist API", version="0.0.1")
app.include_router(profile.router)
app.include_router(recommend.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(MissingMLDependencies)
async def missing_ml_handler(_request: Request, _exc: MissingMLDependencies) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The embedding model is not installed in this API process. Run the API with the ML "
            "dependencies (`make install-ml && make dev`), or use the opt-in `api-ml` container."
        },
    )


class Health(BaseModel):
    status: Literal["ok"]
    db: Literal["ok", "unavailable"]


def get_db_check() -> DbCheck:
    return check_db


@app.get("/health", response_model=Health)
def health(db_check: Annotated[DbCheck, Depends(get_db_check)]) -> Health:
    """Liveness plus DB reachability. The API is 'ok' even if the DB is down; `db` says which."""
    return Health(status="ok", db="ok" if db_check() else "unavailable")
