"""Additive mobile routes, sharing legacy auth and runtime dependencies."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app.api.delivery_contracts import RunCreate
from app.api.delivery_presentation import overview


def build_router(runtime_dependency, auth_dependency, idempotency_dependency):
    router = APIRouter(dependencies=[Depends(auth_dependency)])

    def service(runtime=Depends(runtime_dependency)):
        value = getattr(runtime, "delivery", None)
        if value is None:
            raise HTTPException(503, detail={"code": "delivery_unavailable", "message": "persistent Android delivery runtime is required"})
        return value

    @router.get("/v1/overview")
    def get_overview(start_date: str | None = None, end_date: str | None = None, delivery=Depends(service)):
        try:
            return overview(start_date, end_date)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_context", "message": str(exc)})

    @router.post("/v1/threads/{thread_id}/runs")
    def create_run(thread_id: str, body: RunCreate, response: Response,
                   key: str = Depends(idempotency_dependency), delivery=Depends(service)):
        run, created = delivery.create_run(thread_id, body, key)
        response.status_code = 202 if created else 200
        return run

    @router.get("/v1/runs")
    def list_runs(limit: int = 20, cursor: str | None = None, delivery=Depends(service)):
        return delivery.repo.list_runs(limit=limit, cursor=cursor)

    @router.get("/v1/memories")
    def list_memories(status: str | None = None, limit: int = 50, cursor: str | None = None, delivery=Depends(service)):
        return delivery.repo.list_memories(status=status, limit=limit, cursor=cursor)

    @router.get("/v1/runs/{run_id}/events")
    def events(run_id: str, request: Request, last_event_id: str | None = Header(default=None), delivery=Depends(service)):
        after = delivery.validate_cursor(run_id, last_event_id)
        return StreamingResponse(delivery.event_stream(run_id, after=after, request=request),
                                 media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return router
