"""
Agent Router - 命令行入口
"""
import sys
import json
import argparse
from pathlib import Path

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))


def cmd_serve(args):
    """启动 API 服务器"""
    import uvicorn
    uvicorn.run(
        "src.api.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def cmd_route(args):
    """单次路由请求"""
    from src.api.server import init_engine, get_engine

    init_engine(use_audit=True, use_tracer=True)
    engine = get_engine()

    from src.core.schemas.request import RouterRequest, Message, MessageRole

    # 读取输入
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        request = RouterRequest(**data)
    elif args.prompt:
        request = RouterRequest(
            messages=[Message(role=MessageRole.USER, content=args.prompt)],
        )
    else:
        text = sys.stdin.read().strip()
        if not text:
            print("错误: 请通过 --prompt、--file 或标准输入提供内容")
            sys.exit(1)
        request = RouterRequest(
            messages=[Message(role=MessageRole.USER, content=text)],
        )

    # 执行路由
    import asyncio
    response = asyncio.run(engine.route(request))

    # 输出结果
    if args.verbose:
        print("=" * 60)
        print(f"状态: {response.status.value}")
        print(f"消息: {response.status_message}")
        if response.receipt:
            print(response.receipt.pretty_print())
        if response.model_response:
            print("-" * 60)
            print("模型输出:")
            print(response.model_response.content[:2000])
        print("=" * 60)
    else:
        result = {
            "status": response.status.value,
            "model": response.receipt.selected_model if response.receipt else "N/A",
            "decision_reason": response.receipt.decision_reason.value if response.receipt else "N/A",
            "cost": response.receipt.estimated_cost.total_cost if response.receipt else 0,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_audit(args):
    """查询审计日志"""
    from src.api.server import init_engine
    init_engine(use_audit=True, use_tracer=True)

    from src.api.server import get_audit_logger
    audit = get_audit_logger()

    if args.request_id:
        result = audit.get_by_request(args.request_id)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"未找到请求 {args.request_id} 的审计记录")
    elif args.stats:
        stats = audit.stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        results = audit.query(
            model=args.model,
            decision_reason=args.reason,
            limit=args.limit,
        )
        print(json.dumps(results, ensure_ascii=False, indent=2))


def cmd_trace(args):
    """查询链路追踪"""
    from src.api.server import init_engine
    init_engine(use_audit=True, use_tracer=True)

    from src.api.server import get_tracer
    tracer = get_tracer()

    if args.trace_id:
        result = tracer.get_trace(args.trace_id)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"未找到追踪 {args.trace_id}")
    else:
        results = tracer.recent_traces(limit=args.limit)
        print(json.dumps(results, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Agent Router - 智能路由网关")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # serve
    p_serve = subparsers.add_parser("serve", help="启动 API 服务器")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true", default=True)

    # route
    p_route = subparsers.add_parser("route", help="执行路由请求")
    p_route.add_argument("--prompt", help="用户输入文本")
    p_route.add_argument("--file", help="从 JSON 文件加载请求")
    p_route.add_argument("--verbose", "-v", action="store_true", help="详细输出")

    # audit
    p_audit = subparsers.add_parser("audit", help="查询审计日志")
    p_audit.add_argument("--request-id", help="按请求 ID 查询")
    p_audit.add_argument("--model", help="按模型筛选")
    p_audit.add_argument("--reason", help="按决策原因筛选")
    p_audit.add_argument("--stats", action="store_true", help="显示统计信息")
    p_audit.add_argument("--limit", type=int, default=20)

    # trace
    p_trace = subparsers.add_parser("trace", help="查询链路追踪")
    p_trace.add_argument("--trace-id", help="按追踪 ID 查询")
    p_trace.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "route":
        cmd_route(args)
    elif args.command == "audit":
        cmd_audit(args)
    elif args.command == "trace":
        cmd_trace(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()