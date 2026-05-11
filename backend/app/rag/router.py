import json
import re
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.models.config import LLMConfig
from app.rag.schemas import QueryAnalysis, QueryRoute
from app.services.llm_factory import create_chat_model, uses_mock_provider


FACT_PATTERNS = re.compile(r"(多少钱|价格|票价|门票|开放时间|几点|地址|电话|多久|距离|哪天|日期|事实|多少|price|cost|when|where)", re.I)
GRAPH_PATTERNS = re.compile(r"(谁|旁边|附近|关系|规划师|属于|连接|路线|酒店|景点|人物|near|beside|who|route|hotel)", re.I)
CONCEPT_PATTERNS = re.compile(r"(体验|感觉|适合|推荐|如何|为什么|风格|氛围|概念|大概|experience|recommend|why|how)", re.I)


class QueryAnalyzer:
    def analyze(self, query: str, llm_config: Optional[LLMConfig] = None) -> QueryAnalysis:
        if llm_config is not None and not uses_mock_provider(llm_config):
            llm_result = self._analyze_with_llm(query, llm_config)
            if llm_result is not None:
                return llm_result
        return self._analyze_with_rules(query)

    def _analyze_with_rules(self, query: str) -> QueryAnalysis:
        routes: List[QueryRoute] = []
        reasons: List[str] = []
        if CONCEPT_PATTERNS.search(query):
            routes.append("vector")
            reasons.append("query asks for experience/recommendation semantics")
        if FACT_PATTERNS.search(query):
            routes.append("keyword")
            reasons.append("query asks for factual or exact information")
        if GRAPH_PATTERNS.search(query):
            routes.append("graph")
            reasons.append("query mentions entities, nearby places, people, or routes")
        if not routes:
            routes = ["vector", "keyword"]
            reasons.append("general query, use hybrid vector and keyword retrieval")
        return QueryAnalysis(routes=routes, reasoning="; ".join(reasons))

    def _analyze_with_llm(self, query: str, llm_config: LLMConfig) -> Optional[QueryAnalysis]:
        prompt = (
            "Classify a travel RAG query into one or more routes: vector, keyword, graph. "
            "Return only JSON like {\"routes\":[\"vector\"],\"reasoning\":\"...\"}. "
            "vector=conceptual/semantic, keyword=factual/exact, graph=entity relationship/nearby/route."
        )
        try:
            model = create_chat_model(llm_config)
            response = model.invoke([SystemMessage(content=prompt), HumanMessage(content=query)])
            raw = str(response.content)
            match = re.search(r"\{.*\}", raw, re.S)
            payload = json.loads(match.group(0) if match else raw)
            routes = [route for route in payload.get("routes", []) if route in {"vector", "keyword", "graph"}]
            if routes:
                return QueryAnalysis(routes=routes, reasoning=str(payload.get("reasoning") or "llm classified"))
        except Exception:
            return None
        return None
