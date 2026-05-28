import os
import logging
import json
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, Depends, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy import Column, Integer, String, Boolean, DateTime, text, select
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# ── Structured JSON logging ───────────────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "level":     record.levelname,
            "message":   record.getMessage(),
            "module":    record.module,
        })

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv() 
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL missing. Check .env or CI config.")

REDIS_URL     = os.getenv("REDIS_URL",     "redis://redis:6379/0")
APP_ENV       = os.getenv("APP_ENV",       "production")

# ── Database ──────────────────────────────────────────────────────────────────
engine            = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Task(Base):
    __tablename__ = "tasks"
    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    done        = Column(Boolean, default=False, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ── Redis singleton ───────────────────────────────────────────────────────────
redis_client: aioredis.Redis | None = None

async def get_redis() -> aioredis.Redis:
    return redis_client

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    logger.info("Starting up…")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info("DB ready · Redis connected")
    yield
    await redis_client.aclose()
    await engine.dispose()
    logger.info("Shutdown complete")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Task Manager API",
    description="A production-ready task management API built with FastAPI, PostgreSQL, and Redis.",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start    = datetime.utcnow()
    response = await call_next(request)
    ms       = (datetime.utcnow() - start).total_seconds() * 1000
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({ms:.1f}ms)")
    return response

# ── Schemas ───────────────────────────────────────────────────────────────────
class TaskCreate(BaseModel):
    title:       str         = Field(..., min_length=1, max_length=255, examples=["Buy groceries"])
    description: Optional[str] = Field(None, max_length=1000, examples=["Milk, eggs, bread"])

class TaskUpdate(BaseModel):
    title:       Optional[str]  = Field(None, min_length=1, max_length=255)
    description: Optional[str]  = Field(None, max_length=1000)
    done:        Optional[bool] = None

class TaskResponse(BaseModel):
    id:          int
    title:       str
    description: Optional[str]
    done:        bool
    created_at:  datetime
    updated_at:  datetime

    class Config:
        from_attributes = True

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"], summary="Liveness + readiness probe")
async def health_check(
    db:    AsyncSession    = Depends(get_db),
    redis: aioredis.Redis  = Depends(get_redis),
):
    result = {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
    try:
        await db.execute(text("SELECT 1"))
        result["database"] = "ok"
    except Exception as e:
        result["database"] = f"error: {e}"
        result["status"]   = "degraded"
    try:
        await redis.ping()
        result["redis"] = "ok"
    except Exception as e:
        result["redis"]  = f"error: {e}"
        result["status"] = "degraded"

    return JSONResponse(result, status_code=200 if result["status"] == "ok" else 503)

@app.get("/", tags=["ops"])
async def root():
    return {"message": "Task Manager API", "docs": "/docs", "health": "/health"}

# ── Tasks CRUD ────────────────────────────────────────────────────────────────
CACHE_TTL = 60   # seconds

@app.post("/tasks", response_model=TaskResponse, status_code=201, tags=["tasks"])
async def create_task(
    payload: TaskCreate,
    db:      AsyncSession   = Depends(get_db),
    redis:   aioredis.Redis = Depends(get_redis),
):
    task = Task(title=payload.title, description=payload.description)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    await redis.delete("tasks:all")        # bust list cache
    logger.info(f"Created task id={task.id}")
    return task

@app.get("/tasks", response_model=list[TaskResponse], tags=["tasks"])
async def list_tasks(
    done:  Optional[bool] = Query(None, description="Filter by completion status"),
    db:    AsyncSession   = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cache_key = f"tasks:all:{done}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    q = select(Task).order_by(Task.created_at.desc())
    if done is not None:
        q = q.where(Task.done == done)
    rows  = (await db.execute(q)).scalars().all()
    data  = [
        {"id": t.id, "title": t.title, "description": t.description,
         "done": t.done, "created_at": t.created_at.isoformat(),
         "updated_at": t.updated_at.isoformat()}
        for t in rows
    ]
    await redis.setex(cache_key, CACHE_TTL, json.dumps(data))
    return rows

@app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"])
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task

@app.patch("/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"])
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    db:      AsyncSession   = Depends(get_db),
    redis:   aioredis.Redis = Depends(get_redis),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    task.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    await redis.delete("tasks:all:None", "tasks:all:True", "tasks:all:False")
    logger.info(f"Updated task id={task_id}")
    return task

@app.delete("/tasks/{task_id}", status_code=204, tags=["tasks"])
async def delete_task(
    task_id: int,
    db:      AsyncSession   = Depends(get_db),
    redis:   aioredis.Redis = Depends(get_redis),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    await db.delete(task)
    await db.commit()
    await redis.delete("tasks:all:None", "tasks:all:True", "tasks:all:False")
    logger.info(f"Deleted task id={task_id}")

# ── Stats endpoint (uses Redis counter) ──────────────────────────────────────
@app.get("/tasks/stats/summary", tags=["tasks"])
async def task_stats(
    db:    AsyncSession   = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cached = await redis.get("tasks:stats")
    if cached:
        return json.loads(cached)

    total  = (await db.execute(text("SELECT COUNT(*) FROM tasks"))).scalar()
    done   = (await db.execute(text("SELECT COUNT(*) FROM tasks WHERE done = TRUE"))).scalar()
    result = {"total": total, "done": done, "pending": total - done}
    await redis.setex("tasks:stats", 30, json.dumps(result))
    return result


@app.get("/ai")
def ai_demo():
    return {
        "message": "AI/LLM endpoint placeholder",
        "status": "ready for OpenAI integration"
    }
