import time
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


# ============================================================
# Span
# ============================================================

@dataclass
class Span:
    """追踪 span"""
    name: str
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "ok"  # ok / error

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def finish(self, status: str = "ok", metadata: Optional[Dict[str, Any]] = None):
        self.end_time = time.time()
        self.status = status
        if metadata:
            self.metadata.update(metadata)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "metadata": self.metadata,
        }


# ============================================================
# Trace
# ============================================================

@dataclass
class Trace:
    """一次完整的追踪"""
    trace_id: str
    request_id: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    spans: List[Span] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_span(
        self,
        name: str,
        parent_span_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """创建子 span"""
        span = Span(
            name=name,
            trace_id=self.trace_id,
            span_id=f"{self.trace_id}.{len(self.spans)+1}",
            parent_span_id=parent_span_id,
            metadata=metadata or {},
        )
        self.spans.append(span)
        return span

    def finish(self):
        self.end_time = time.time()

    @property
    def total_duration_ms(self) -> float:
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "total_duration_ms": round(self.total_duration_ms, 3),
            "spans": [s.to_dict() for s in self.spans],
            "metadata": self.metadata,
        }


# ============================================================
# 追踪器
# ============================================================

class Tracer:
    """
    链路追踪器

    用法:
        tracer = Tracer()

        # 在 engine.route() 中:
        await tracer.start_trace(trace_id, request)
        span = tracer.start_span(trace_id, "feature_extraction")
        # ... 特征提取 ...
        tracer.end_span(span)

        tracer.end_trace(trace_id, response)
    """

    def __init__(
        self,
        log_dir: Optional[str] = None,
        console: bool = False,
        enabled: bool = True,
    ):
        self.log_dir = Path(log_dir) if log_dir else None
        self.console = console
        self.enabled = enabled

        self._active_traces: Dict[str, Trace] = {}
        self._completed_traces: List[Trace] = []
        self._max_completed = 1000

        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------
    # 公共 API
    # ----------------------------------------------------------

    async def start_trace(self, trace_id: str, request: Any):
        """开始一次追踪 (对接 engine._trace_start)"""
        if not self.enabled:
            return

        request_id = getattr(request, "request_id", "")
        trace = Trace(trace_id=trace_id, request_id=request_id)
        self._active_traces[trace_id] = trace

        # 创建根 span
        trace.add_span(name="router_request", metadata={"request_id": request_id})

        if self.console:
            print(f"[TRACE] START {trace_id} request={request_id}")

    async def end_trace(self, trace_id: str, response: Any):
        """结束一次追踪 (对接 engine._trace_end)"""
        if not self.enabled:
            return

        trace = self._active_traces.pop(trace_id, None)
        if trace is None:
            return

        # 结束所有未关闭的 span
        for span in trace.spans:
            if span.end_time is None:
                span.finish()

        trace.finish()

        # 加入已完成列表
        self._completed_traces.append(trace)
        if len(self._completed_traces) > self._max_completed:
            self._completed_traces = self._completed_traces[-self._max_completed:]

        # 持久化
        if self.log_dir:
            self._persist_trace(trace)

        if self.console:
            print(f"[TRACE] END   {trace_id} total={trace.total_duration_ms:.1f}ms")

    def start_span(
        self,
        trace_id: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Span]:
        """开始一个 span"""
        if not self.enabled:
            return None

        trace = self._active_traces.get(trace_id)
        if trace is None:
            return None

        span = trace.add_span(name=name, metadata=metadata)

        if self.console:
            print(f"[TRACE] SPAN  {trace_id} {name}")

        return span

    def end_span(self, span: Optional[Span], status: str = "ok"):
        """结束一个 span"""
        if span is None:
            return
        span.finish(status=status)

    # ----------------------------------------------------------
    # 查询
    # ----------------------------------------------------------

    def get_trace(self, trace_id: str) -> Optional[dict]:
        """按 trace_id 查询"""
        # 先查活跃的
        trace = self._active_traces.get(trace_id)
        if trace:
            return trace.to_dict()

        # 再查已完成的
        for t in reversed(self._completed_traces):
            if t.trace_id == trace_id:
                return t.to_dict()

        return None

    def recent_traces(self, limit: int = 20) -> List[dict]:
        """最近的追踪记录"""
        results = []

        # 活跃的在前
        for t in reversed(list(self._active_traces.values())):
            results.append(t.to_dict())
            if len(results) >= limit:
                return results[:limit]

        # 已完成的
        for t in reversed(self._completed_traces):
            results.append(t.to_dict())
            if len(results) >= limit:
                return results[:limit]

        return results

    def stats(self) -> dict:
        """追踪统计"""
        all_traces = list(self._active_traces.values()) + self._completed_traces

        if not all_traces:
            return {"total": 0}

        durations = [t.total_duration_ms for t in all_traces]

        return {
            "total": len(all_traces),
            "active": len(self._active_traces),
            "completed": len(self._completed_traces),
            "avg_duration_ms": round(sum(durations) / len(durations), 1),
            "min_duration_ms": round(min(durations), 1),
            "max_duration_ms": round(max(durations), 1),
        }

    # ----------------------------------------------------------
    # 内部
    # ----------------------------------------------------------

    def _persist_trace(self, trace: Trace):
        """持久化到文件"""
        if not self.log_dir:
            return

        filepath = self.log_dir / f"trace-{trace.trace_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(trace.to_dict(), f, ensure_ascii=False, indent=2)

    def __repr__(self) -> str:
        return (
            f"Tracer(enabled={self.enabled}, "
            f"active={len(self._active_traces)}, "
            f"completed={len(self._completed_traces)})"
        )

"""
============================================================
接口速查
============================================================

class Span:
    name, trace_id, span_id, parent_span_id
    duration_ms (property)
    finish(status, metadata)
    to_dict() -> dict

class Trace:
    trace_id, request_id, spans
    add_span(name, parent_span_id, metadata) -> Span
    finish()
    total_duration_ms (property)
    to_dict() -> dict

class Tracer:
    __init__(log_dir=None, console=False, enabled=True)

    async start_trace(trace_id, request)     # engine hook
    async end_trace(trace_id, response)       # engine hook
    start_span(trace_id, name, metadata) -> Span | None
    end_span(span, status="ok")

    get_trace(trace_id) -> dict | None
    recent_traces(limit=20) -> List[dict]
    stats() -> dict
"""