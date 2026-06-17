from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import images, registries
from app.core.auth import CurrentUser
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="PatchPilot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(registries.router)
app.include_router(images.router)


@app.get("/api/me")
async def me(user: CurrentUser) -> dict:
    return {
        "sub": user["sub"],
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "roles": user.get("realm_access", {}).get("roles", []),
        "teams": user.get("patchpilot_teams", []),
    }


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
