import json
import re
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.models.config import LLMConfig
from app.rag.schemas import QueryAnalysis, QueryRoute
from app.services.llm_factory import create_chat_model, uses_mock_provider


FACT_PATTERNS = re.compile(r"(多少钱|价格|票价|门票|开放时间|几点|地址|电话|多久|距离|哪天|日期|事实|多少|price|cost|when|where)", re.I)
GRAPH_PATTERNS = re.compile(r"(谁|旁边|附近|关系|规划师|属于|连接|路线|酒店|景点|人物|near|beside|who|route|hotel)", re.I)
CONCEPT_PATTERNS = re.compile(r"(体验|感觉|适合|推荐|如何|为什么|风格|氛围|概念|大概|experience|recommend|why|how)", re.I)


class QueryAnalyzer:
    def analyze(self, query: str, llm_config: Optional[LLMConfig] = None) -> QueryAnalysis:
        # 聊天首 token 慢的一个主要原因是:每轮正式回答前先额外调用一次
        # LLM 做 RAG 路由分类。这里改成规则路由,把慢调用留给真正回答。
        # _analyze_with_llm 保留给后续离线调试/评估使用。
        return self._analyze_with_rules(query)

    def _analyze_with_rules(self, query: str) -> QueryAnalysis:
        routes: List[QueryRoute] = []
        reasons: List[str] = []
        weights: Dict[QueryRoute, float] = {}
        if CONCEPT_PATTERNS.search(query):
            routes.append("vector")
            weights["vector"] = max(weights.get("vector", 0.0), 0.65)
            reasons.append("query asks for experience/recommendation semantics")
        if FACT_PATTERNS.search(query):
            routes.append("keyword")
            weights["keyword"] = max(weights.get("keyword", 0.0), 0.8)
            reasons.append("query asks for factual or exact information")
        if GRAPH_PATTERNS.search(query):
            routes.append("graph")
            weights["graph"] = max(weights.get("graph", 0.0), 0.7)
            reasons.append("query mentions entities, nearby places, people, or routes")
        if not routes:
            routes = ["vector", "keyword"]
            weights = {"vector": 0.55, "keyword": 0.45}
            reasons.append("general query, use hybrid vector and keyword retrieval")
        return QueryAnalysis(
            routes=routes,
            reasoning="; ".join(reasons),
            route_weights=self._normalize_weights(routes, weights),
            decision_source="rules",
        )

    def _analyze_with_llm(self, query: str, llm_config: LLMConfig) -> Optional[QueryAnalysis]:
        prompt = (
            "Classify a travel RAG query into one or more routes and assign retrieval weights. "
            "Return only JSON like "
            "{\"routes\":[\"vector\",\"keyword\"],\"weights\":{\"vector\":0.6,\"keyword\":0.4},\"reasoning\":\"...\"}. "
            "Weights must sum to 1 across selected routes. "
            "vector=conceptual/semantic, keyword=factual/exact, graph=entity relationship/nearby/route."
        )
        try:
            model = create_chat_model(llm_config, timeout=8)
            response = model.invoke(
                [SystemMessage(content=prompt), HumanMessage(content=query)],
            )
            raw = str(response.content)
            match = re.search(r"\{.*\}", raw, re.S)
            payload = json.loads(match.group(0) if match else raw)
            routes = [route for route in payload.get("routes", []) if route in {"vector", "keyword", "graph"}]
            if routes:
                raw_weights = payload.get("weights") or payload.get("route_weights") or {}
                weights = {
                    route: float(raw_weights.get(route, 0.0))
                    for route in routes
                    if isinstance(raw_weights, dict)
                }
                return QueryAnalysis(
                    routes=routes,
                    reasoning=str(payload.get("reasoning") or "llm classified"),
                    route_weights=self._normalize_weights(routes, weights),
                    decision_source="llm",
                )
        except Exception:
            return None
        return None

    @staticmethod
    def _normalize_weights(routes: List[QueryRoute], weights: Dict[QueryRoute, float]) -> Dict[QueryRoute, float]:
        route_set = list(dict.fromkeys(routes))
        cleaned = {route: max(0.0, float(weights.get(route, 0.0))) for route in route_set}
        total = sum(cleaned.values())
        if total <= 0:
            even = round(1.0 / max(1, len(route_set)), 4)
            return {route: even for route in route_set}
        normalized = {route: round(value / total, 4) for route, value in cleaned.items()}
        drift = round(1.0 - sum(normalized.values()), 4)
        if route_set and drift:
            normalized[route_set[0]] = round(normalized[route_set[0]] + drift, 4)
        return normalized
