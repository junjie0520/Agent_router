"""
审计日志器
将 RouteReceipt 以结构化格式写入日志
支持: JSON Lines 文件 + 控制台 + 自定义 handler
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Callable, Any

from src.core.schemas.receipt import RouteReceipt
from src.core.audit.receipt import summarize_receipt


# ============================================================
# 审计日志器
# ============================================================

class AuditLogger:
    """
    审计日志器

    用法:
        logger = AuditLogger(log_dir="storage/audit")
        logger.log(receipt)

        # 查询
        results = logger.query(request_id="req-001")
    """

    def __init__(
        self,
        log_dir: str = "storage/audit",
        console: bool = True,
        secret: Optional[str] = None,
        extra_handlers: Optional[List[Callable[[dict], None]]] = None,
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.console = console
        self.secret = secret
        self.extra_handlers = extra_handlers or []

        # 内部计数器
        self.total_logged = 0

        # Python 标准日志
        self._logger = logging.getLogger("audit")
        self._logger.setLevel(logging.INFO)
        if not self._logger.handlers:
            self._logger.addHandler(logging.NullHandler())

    # ----------------------------------------------------------
    # 写入
    # ----------------------------------------------------------

    def log(self, receipt: RouteReceipt) -> Path:
        """
        写入一条审计日志

        做的事情:
          1. 生成摘要
          2. 写入 JSON Lines 文件 (按日期分文件)
          3. 可选: 控制台输出
          4. 可选: 签名
          5. 调用额外 handler

        Args:
            receipt: 路由凭证

        Returns:
            写入的日志文件路径
        """
        # 签名
        if self.secret:
            from src.core.audit.receipt import sign_receipt
            sign_receipt(receipt, self.secret)

        # 生成摘要
        summary = summarize_receipt(receipt)
        summary["logged_at"] = datetime.now().isoformat()

        # 写入 JSON Lines 文件
        filepath = self._daily_file()
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")

        # 控制台输出
        if self.console:
            self._log_console(summary)

        # Python 标准日志
        self._logger.info(
            f"receipt={receipt.receipt_id} "
            f"model={receipt.selected_model} "
            f"reason={receipt.decision_reason.value} "
            f"cost=${receipt.estimated_cost.total_cost:.4f}"
        )

        # 额外 handler
        for handler in self.extra_handlers:
            try:
                handler(summary)
            except Exception:
                pass

        self.total_logged += 1
        return filepath

    def log_batch(self, receipts: List[RouteReceipt]) -> Path:
        """批量写入"""
        filepath = self._daily_file()
        for r in receipts:
            self.log(r)
        return filepath

    # ----------------------------------------------------------
    # 查询
    # ----------------------------------------------------------

    def query(
        self,
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        model: Optional[str] = None,
        decision_reason: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """
        查询审计日志

        Args:
            request_id: 按请求 ID 筛选
            trace_id: 按链路 ID 筛选
            model: 按模型名筛选
            decision_reason: 按决策原因筛选
            date: 按日期筛选 (YYYY-MM-DD)
            limit: 最大返回条数

        Returns:
            匹配的日志摘要列表（最新在前）
        """
        files = self._get_log_files(date)
        results = []

        for filepath in reversed(files):
            if len(results) >= limit:
                break

            if not filepath.exists():
                continue

            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if request_id and record.get("request_id") != request_id:
                        continue
                    if trace_id and record.get("trace_id") != trace_id:
                        continue
                    if model and record.get("selected_model") != model:
                        continue
                    if decision_reason and record.get("decision_reason") != decision_reason:
                        continue

                    results.append(record)
                    if len(results) >= limit:
                        break

        return results

    def get_by_request(self, request_id: str) -> Optional[dict]:
        """按请求 ID 精确查找"""
        results = self.query(request_id=request_id, limit=1)
        return results[0] if results else None

    # ----------------------------------------------------------
    # 统计
    # ----------------------------------------------------------

    def stats(self, date: Optional[str] = None) -> dict:
        """返回审计日志统计"""
        records = self.query(date=date, limit=10000)

        if not records:
            return {"total": 0}

        models = {}
        reasons = {}
        total_cost = 0.0
        fallback_count = 0

        for r in records:
            model = r.get("selected_model", "unknown")
            reason = r.get("decision_reason", "unknown")
            models[model] = models.get(model, 0) + 1
            reasons[reason] = reasons.get(reason, 0) + 1
            total_cost += r.get("estimated_cost_usd", 0)
            if r.get("is_fallback"):
                fallback_count += 1

        return {
            "total": len(records),
            "by_model": models,
            "by_reason": reasons,
            "total_cost_usd": round(total_cost, 4),
            "fallback_count": fallback_count,
            "fallback_rate": round(fallback_count / len(records), 3) if records else 0,
        }

    # ----------------------------------------------------------
    # 内部
    # ----------------------------------------------------------

    def _daily_file(self) -> Path:
        """当天日志文件路径"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"audit-{date_str}.jsonl"

    def _get_log_files(self, date: Optional[str] = None) -> List[Path]:
        """获取日志文件列表"""
        if date:
            return [self.log_dir / f"audit-{date}.jsonl"]

        files = sorted(
            self.log_dir.glob("audit-*.jsonl"),
            key=lambda p: p.name,
            reverse=True,
        )
        return files

    def _log_console(self, summary: dict):
        """控制台输出"""
        status = "FALLBACK" if summary.get("is_fallback") else "OK"
        print(
            f"[AUDIT] {summary['logged_at']} | "
            f"{summary['request_id']} | "
            f"{summary['selected_model']} | "
            f"{summary['decision_reason']} | "
            f"${summary['estimated_cost_usd']:.4f} | "
            f"{status}"
        )

    def __repr__(self) -> str:
        return f"AuditLogger(log_dir={self.log_dir}, total={self.total_logged})"

"""
============================================================
接口速查
============================================================

class AuditLogger:
    __init__(log_dir, console=True, secret=None, extra_handlers=None)
    log(receipt) -> Path
    log_batch(receipts) -> Path
    query(request_id, trace_id, model, decision_reason, date, limit) -> List[dict]
    get_by_request(request_id) -> Optional[dict]
    stats(date) -> dict

文件格式:
  storage/audit/audit-2026-07-19.jsonl  (每行一个 JSON 摘要)

============================================================
"""
"""
链路追踪器
基于 trace_id 串联全链路各阶段的耗时
与 engine.py 的预留 hook 对接
"""