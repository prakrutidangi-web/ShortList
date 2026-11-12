from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shortlist_api.config import get_settings
from shortlist_api.db import DbCheck, check_db

app = FastAPI(title="Shortlist API", version="0.0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
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
