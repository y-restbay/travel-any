import re
from typing import List


LATIN_ENTITY_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9_\- ]{2,40}\b")
CJK_ENTITY_PATTERN = re.compile(
    r"[\u4e00-\u9fff]{2,8}(?:迪士尼|影城|海游馆|寺|神社|公园|博物馆|机场|车站|站|酒店|河原町|坂|梅田|难波)"
    r"|(?:东京|大阪|京都|梅田|难波|舞滨站|清水寺|二年坂|四条河原町|环球影城|海游馆)"
)

GENERIC_ENTITIES = {
    "门票",
    "酒店",
    "路线",
    "景点",
    "价格",
    "日期",
    "父母",
    "孩子",
    "亲子",
    "雨天",
    "自然",
    "风景",
}


class EntityExtractor:
    def extract(self, text: str) -> List[str]:
        entities: List[str] = []
        seen: set = set()
        matches = LATIN_ENTITY_PATTERN.findall(text) + CJK_ENTITY_PATTERN.findall(text)
        for match in matches:
            entity = match.strip(" -_，。,.：:")
            if len(entity) < 2 or len(entity) > 20 or entity in seen or entity in GENERIC_ENTITIES:
                continue
            seen.add(entity)
            entities.append(entity)
            if len(entities) >= 12:
                break
        return entities
