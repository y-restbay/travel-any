#!/usr/bin/env python3
"""End-to-end RAG workflow verification for the local WanderBot prototype."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db.base import Base
from app.db.migrations import run_lightweight_migrations
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.config import LLMConfig
from app.rag import get_rag_pipeline
from app.schemas.chat import ChatMessage
from app.services.chat_service import chat_stream
from app.services.config_service import ensure_defaults, get_active_llm_config, get_active_system_prompt


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def parse_sse_frame(frame: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    event = None
    data = None
    for line in frame.splitlines():
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            data = json.loads(line[6:])
    return event, data


def ensure_mock_config(db) -> Tuple[Optional[int], int, bool]:
    previous = get_active_llm_config(db)
    mock = (
        db.query(LLMConfig)
        .filter(LLMConfig.provider == "Mock")
        .order_by(LLMConfig.id)
        .first()
    )
    created = False
    if mock is None:
        mock = LLMConfig(
            provider="Mock",
            model_name="wanderbot-mock-rag-check",
            api_key="",
            base_url="",
            is_active=False,
        )
        db.add(mock)
        db.commit()
        db.refresh(mock)
        created = True

    db.query(LLMConfig).update({"is_active": False})
    mock.is_active = True
    db.commit()
    return previous.id if previous else None, mock.id, created


def restore_active_config(db, previous_id: Optional[int], temporary_mock_id: Optional[int], created_mock: bool) -> None:
    if previous_id is None:
        return
    db.query(LLMConfig).update({"is_active": False})
    previous = db.get(LLMConfig, previous_id)
    if previous is not None:
        previous.is_active = True
    if created_mock and temporary_mock_id is not None:
        temporary = db.get(LLMConfig, temporary_mock_id)
        if temporary is not None and temporary.id != previous_id:
            db.delete(temporary)
    db.commit()


async def collect_chat_stream(messages: list[ChatMessage], llm_config: LLMConfig, system_prompt) -> Tuple[Dict[str, Any], str]:
    meta: Dict[str, Any] = {}
    answer_parts: list = []
    async for frame in chat_stream(messages, llm_config, system_prompt):
        event, data = parse_sse_frame(frame)
        if event == "meta" and data:
            meta = data
        elif event == "delta" and data:
            answer_parts.append(str(data.get("content") or ""))
        elif event == "error" and data:
            raise RuntimeError(str(data.get("message") or data))
    return meta, "".join(answer_parts)


def run_http_api_checks(marker: str) -> Dict[str, Any]:
    upload_text = (
        f"{marker}-upload\n"
        "东京迪士尼成人一日票价格通常随日期波动，常见区间约为7900到10900日元。"
        "舞滨站旁边有适合亲子家庭的酒店，适合需要减少交通折返的游客。"
    )
    with TestClient(app) as client:
        upload_response = client.post(
            "/api/rag/ingest/upload",
            data={"doc_type": "guide", "source": "api-e2e-test"},
            files={"file": (f"{marker}-upload.txt", upload_text.encode("utf-8"), "text/plain")},
        )
        assert_true(upload_response.status_code == 200, f"upload API failed: {upload_response.text}")
        upload = upload_response.json()
        assert_true(upload["chunk_count"] >= 1, "upload API 未产生切片")

        debug_response = client.post(
            "/api/rag/debug",
            json={"query": f"东京迪士尼门票是多少钱？旁边有什么酒店？资料标记 {marker}-upload", "top_k": 5},
        )
        assert_true(debug_response.status_code == 200, f"debug API failed: {debug_response.text}")
        debug = debug_response.json()
        assert_true([step["step"] for step in debug["trace"]] == ["step_1", "step_2", "step_3", "step_4"], "debug API 四步 trace 不完整")
        assert_true(debug["retrieve_result"]["context_block"], "debug API 未生成注入上下文")

        chat_response = client.post(
            "/api/chat/stream",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": f"东京迪士尼门票是多少钱？旁边有什么酒店？资料标记 {marker}-upload",
                    }
                ]
            },
        )
        assert_true(chat_response.status_code == 200, f"chat stream API failed: {chat_response.text}")
        meta: Dict[str, Any] = {}
        answer = []
        for frame in chat_response.text.split("\n\n"):
            event, data = parse_sse_frame(frame)
            if event == "meta" and data:
                meta = data
            elif event == "delta" and data:
                answer.append(str(data.get("content") or ""))
        assert_true(meta.get("rag_context_injected") is True, "chat API SSE meta 未标记 RAG 注入")
        assert_true(bool(meta.get("rag_sources")), "chat API SSE meta 未返回来源")

    return {
        "upload_chunks": upload["chunk_count"],
        "debug_steps": [step["step"] for step in debug["trace"]],
        "debug_routes": debug["retrieve_result"]["analysis"]["routes"],
        "debug_weights": debug["retrieve_result"]["analysis"]["route_weights"],
        "chat_runtime": meta.get("runtime"),
        "chat_context_injected": meta.get("rag_context_injected"),
        "chat_answer_chars": len("".join(answer)),
    }


async def main() -> None:
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations(engine)

    with SessionLocal() as db:
        ensure_defaults(db)
        previous_id, temporary_mock_id, created_mock = ensure_mock_config(db)
        try:
            pipeline = get_rag_pipeline()
            before = pipeline.stats()
            before_vectors = int(before.get("vector_count") or 0)

            marker = f"rag-e2e-{uuid.uuid4().hex[:8]}"
            document_text = (
                f"{marker}\n"
                "冰岛第一次旅行建议以南岸自然风景为主。中等预算、三个人出行时，"
                "建议雷克雅未克落地后自驾黄金圈、塞里雅兰瀑布、斯科加瀑布、维克黑沙滩和冰川湖。"
                "三人可以优先选择带厨房的公寓或小木屋来分摊住宿和餐饮成本。"
                "如果冬季出发，单日车程要保守，天气不好时不要强行赶路。"
            )
            ingest = pipeline.ingest_text(
                document_text,
                filename=f"{marker}.txt",
                metadata={"doc_type": "guide", "source": "rag-e2e-test"},
            )
            assert_true(ingest.strategy == "long_form", "guide 文档应走 long_form 自适应切片策略")
            assert_true(ingest.chunk_count >= 1, "上传文档必须至少产生 1 个切片")

            after = pipeline.stats()
            assert_true(int(after.get("vector_count") or 0) >= before_vectors + ingest.chunk_count, "Chroma 向量数量没有按切片增加")
            assert_true(int(after.get("chunk_count") or 0) >= ingest.chunk_count, "BM25 chunk 计数没有更新")

            query = f"第一次去冰岛，预算中等，想看自然风景，3个人。资料标记 {marker}"
            debug = pipeline.debug_retrieve(query, llm_config=get_active_llm_config(db), top_k=5)
            steps = [step.step for step in debug.trace]
            assert_true(steps == ["step_1", "step_2", "step_3", "step_4"], f"RAG debug trace 顺序异常: {steps}")
            assert_true(debug.retrieve_result.analysis.routes, "查询路由必须至少选择一种检索方式")
            assert_true(debug.retrieve_result.analysis.route_weights, "查询路由必须给出权重")
            assert_true(abs(sum(debug.retrieve_result.analysis.route_weights.values()) - 1.0) < 0.01, "路由权重总和应接近 1")
            assert_true(debug.retrieve_result.contexts, "召回+重排后没有上下文")
            assert_true(marker in debug.retrieve_result.context_block, "最终 context_block 未包含刚上传的测试资料")

            llm_config = get_active_llm_config(db)
            system_prompt = get_active_system_prompt(db)
            messages = [ChatMessage(role="user", content=query)]
            meta, answer = await collect_chat_stream(messages, llm_config, system_prompt)
            assert_true(meta.get("rag_context_injected") is True, "chat SSE meta 未标记 RAG context 已注入")
            assert_true(marker in {str(source.get("filename", "")) for source in meta.get("rag_sources", [])} or meta.get("rag_sources"), "chat SSE meta 未返回 RAG 来源")
            assert_true("知识库命中" in answer, "Mock 回答未确认知识库命中")
            http_checks = run_http_api_checks(marker)

            report = {
                "status": "passed",
                "document": {
                    "filename": ingest.filename,
                    "strategy": ingest.strategy,
                    "chunks": ingest.chunk_count,
                },
                "storage": {
                    "vectors_before": before_vectors,
                    "vectors_after": after.get("vector_count"),
                    "bm25_chunks": after.get("chunk_count"),
                },
                "routing": {
                    "decision_source": debug.retrieve_result.analysis.decision_source,
                    "routes": debug.retrieve_result.analysis.routes,
                    "weights": debug.retrieve_result.analysis.route_weights,
                },
                "retrieval": {
                    "contexts": len(debug.retrieve_result.contexts),
                    "context_injected": bool(debug.retrieve_result.context_block),
                    "top_sources": [
                        {
                            "source": context.source,
                            "score": context.score,
                            "filename": context.metadata.get("filename"),
                        }
                        for context in debug.retrieve_result.contexts[:5]
                    ],
                },
                "chat": {
                    "runtime": meta.get("runtime"),
                    "rag_context_injected": meta.get("rag_context_injected"),
                    "answer_chars": len(answer),
                },
                "http_api": http_checks,
            }
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            restore_active_config(db, previous_id, temporary_mock_id, created_mock)


if __name__ == "__main__":
    asyncio.run(main())
