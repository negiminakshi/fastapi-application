"""
Unit tests for Task Manager API.
Run locally: pytest app/tests/ -v
CI runs these automatically on every push.
"""
import pytest
from unittest.mock import AsyncMock, patch

# ── Helpers ───────────────────────────────────────────────────────────────────
class FakeDB:
    """Minimal async DB session stub."""
    async def execute(self, *a, **kw):
        raise Exception("no real DB in unit tests")
    async def get(self, *a, **kw): return None
    def add(self, *a): pass
    async def commit(self): pass
    async def refresh(self, obj): pass
    async def delete(self, *a): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass

class FakeRedis:
    """Minimal async Redis stub."""
    _store: dict = {}
    async def ping(self): return True
    async def get(self, k): return self._store.get(k)
    async def set(self, k, v): self._store[k] = v
    async def setex(self, k, ttl, v): self._store[k] = v
    async def delete(self, *keys):
        for k in keys: self._store.pop(k, None)

# ── Tests ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_health_ok():
    from main import health_check
    db    = AsyncMock()
    redis = FakeRedis()
    resp  = await health_check(db=db, redis=redis)
    assert resp.status_code == 200
    import json
    body = json.loads(resp.body)
    assert body["status"] == "ok"
    assert body["redis"]  == "ok"

@pytest.mark.asyncio
async def test_health_degraded_on_db_error():
    from main import health_check
    db = AsyncMock()
    db.execute.side_effect = Exception("connection refused")
    redis = FakeRedis()
    resp  = await health_check(db=db, redis=redis)
    assert resp.status_code == 503
    import json
    assert json.loads(resp.body)["status"] == "degraded"

@pytest.mark.asyncio
async def test_get_task_not_found():
    from main import get_task
    db = AsyncMock()
    db.get.return_value = None
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await get_task(task_id=999, db=db)
    assert exc.value.status_code == 404
