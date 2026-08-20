"""
API 路由端点
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.core.schemas.request import RouterRequest
from src.core.schemas.response import RouterResponse

router = APIRouter()


@router.post("/route", response_model=RouterResponse)
async def route_request(request: RouterRequest):
    """路由请求"""
    from src.api.server import get_engine
    engine = get_engine()
    response = await engine.route(request)
    return response


@router.get("/health")
async def health_check():
    """健康检查"""
    from src.api.server import get_engine
    engine = get_engine()
    stats = engine.get_stats()
    return {
        "status": "ok",
        "total_requests": stats["engine"]["total_requests"],
        "success_rate": stats["engine"]["success_rate"],
    }


@router.get("/stats")
async def engine_stats():
    """引擎统计"""
    from src.api.server import get_engine
    engine = get_engine()
    return engine.get_stats()


@router.get("/audit/{request_id}")
async def audit_query(request_id: str):
    """按请求 ID 查询审计日志"""
    from src.api.server import get_audit_logger
    audit = get_audit_logger()
    if audit is None:
        raise HTTPException(status_code=503, detail="审计日志未启用")
    result = audit.get_by_request(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="未找到该请求的审计记录")
    return result


@router.get("/audit")
async def audit_list(
    model: Optional[str] = Query(None),
    decision_reason: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """查询审计日志列表"""
    from src.api.server import get_audit_logger
    audit = get_audit_logger()
    if audit is None:
        raise HTTPException(status_code=503, detail="审计日志未启用")
    results = audit.query(model=model, decision_reason=decision_reason, limit=limit)
    return {"total": len(results), "items": results}


@router.get("/trace/{trace_id}")
async def trace_query(trace_id: str):
    """按链路 ID 查询追踪"""
    from src.api.server import get_tracer
    tracer = get_tracer()
    if tracer is None:
        raise HTTPException(status_code=503, detail="链路追踪未启用")
    result = tracer.get_trace(trace_id)
    if result is None:
        raise HTTPException(status_code=404, detail="未找到该追踪记录")
    return result


@router.get("/trace")
async def trace_list(limit: int = Query(20, ge=1, le=100)):
    """最近的追踪记录"""
    from src.api.server import get_tracer
    tracer = get_tracer()
    if tracer is None:
        raise HTTPException(status_code=503, detail="链路追踪未启用")
    results = tracer.recent_traces(limit=limit)
    return {"total": len(results), "items": results}