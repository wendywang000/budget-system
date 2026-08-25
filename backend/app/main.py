from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import auth, budget, capex, excel, expense, masters, permissions, reports, sales

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(masters.router, prefix=settings.api_prefix)
app.include_router(budget.router, prefix=settings.api_prefix)
app.include_router(reports.router, prefix=settings.api_prefix)
app.include_router(excel.router, prefix=settings.api_prefix)
app.include_router(sales.router, prefix=settings.api_prefix)
app.include_router(capex.router, prefix=settings.api_prefix)
app.include_router(expense.router, prefix=settings.api_prefix)
app.include_router(permissions.router, prefix=settings.api_prefix)


@app.get("/api/health", tags=["系統"], summary="健康檢查")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
