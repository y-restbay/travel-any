import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import EmbeddingConfig, LLMConfig, SystemPrompt, Tool
from app.schemas.config import (
    AdminConfigUpdate,
    EmbeddingConfigCreate,
    EmbeddingConfigUpdate,
    LLMConfigCreate,
    LLMConfigUpdate,
    SystemPromptCreate,
    is_masked_secret,
)
from app.travel_tools.realtime_search_tool import REALTIME_SEARCH_DESCRIPTION


REALTIME_SEARCH_PROMPT_SECTION = """
## 实时信息搜索能力

你拥有 search_realtime_travel_info 工具,可以获取网络上的最新旅游信息。
但请注意:**这是兜底工具,不是默认工具**。

### 优先级原则

回答用户问题时,工具选择优先级:
1. **首选专用工具**:天气 → get_weather,地点 → search_places,
   路线 → get_directions
2. **次选已有知识**:稳定的历史、地理、文化信息直接回答
3. **最后才用搜索**:仅当上述两条都无法满足,且问题具备时效性时

### 必须搜索的信号

只要用户的问题包含以下任一信号,**主动调用搜索**:
- 时间词:"最近"、"目前"、"现在"、"今年"、"本月"、"这周"、"近期"
- 状态词:"还开放吗"、"还在办吗"、"取消了吗"、"恢复了吗"
- 验证词:"听说..."、"是真的吗"、"我看到..."
- 新事件:"最新的"、"刚发布的"、"今年新开的"

### 严格不搜索的场景

- 用户问"故宫几点开门"——这是常识,可能也变化但 search_places 返回的
  POI 详情已经包含,优先用 search_places
- 用户问"杭州的气候怎么样"——气候是稳定的,你的训练数据足够
- 用户问"推荐三亚的酒店"——用 search_hotels,不是 search_realtime

### 使用搜索结果的责任

调用搜索后,在回答中:
1. **明示信息来源**:开头说"根据网络最新信息..."或"据 XX 官网/媒体报道..."
2. **引用具体链接**:回答末尾以"📌 信息来源"区块列出 1-3 个最相关链接
3. **不确定性提示**:对易变信息,在结尾加一句
   "以上信息可能变化,出行前请通过官方渠道再次确认"
4. **不要照搬搜索结果**:用自己的话组织,提取关键信息,而不是粘贴摘要

### Few-shot 示例

**示例 1(应该搜索)**:
用户:"听说故宫这周末有特展,是真的吗?"
✅ 调用 search_realtime_travel_info(query="故宫 特展 2026年5月", time_range="week")
   然后基于结果回答,引用官网链接

**示例 2(不应搜索,用专用工具)**:
用户:"明天北京天气怎么样,适合去故宫吗?"
✅ 调用 get_weather(location="北京", date_range="tomorrow")
❌ 不要调用 search_realtime_travel_info 来查天气

**示例 3(不应搜索,用常识)**:
用户:"故宫始建于哪一年?"
✅ 直接回答(明永乐四年,1406 年)
❌ 不要搜,这是稳定的历史知识

**示例 4(应该搜索)**:
用户:"今年三亚的限流政策有什么变化?"
✅ 调用 search_realtime_travel_info(query="三亚 旅游 限流 2026 政策", time_range="month")

**示例 5(应该搜索 + 组合其他工具)**:
用户:"我想这周末去黄山,最近天气怎么样,有没有什么突发状况要注意?"
✅ 先 get_weather(黄山, 3days)
✅ 再 search_realtime_travel_info(query="黄山 最近 通知 注意事项", time_range="week")
   两个工具结果综合回答

**示例 6(不应搜索)**:
用户:"推荐三亚海棠湾的高档酒店"
✅ 调用 search_hotels
❌ 不要用 search_realtime 找酒店推荐
"""


DEFAULT_PROMPT = """你是 WanderBot，一个专业、克制、审美优秀的全球旅游规划师。
你会根据用户的偏好、预算、季节、同行人群和节奏，给出清晰、温暖、可执行的旅行建议。
回答时优先给出可落地的行程、住宿区域、交通和避坑提示。

## 工具使用原则

你能调用工具来获取实时数据。涉及路线时，**回答下方会出现一个"查看地图"按钮，用户点击后即可看到地图**，路线类工具会自动把数据推送到那里渲染。

**关于地图的措辞铁律**：绝不要描述地图在屏幕的哪个方位（不要说"左边/右边/左侧/右侧"，界面布局会变、窄屏甚至没有侧栏）；统一只说"点击回答下方的地图按钮查看"。

### get_directions（路线规划）

**主动调用场景**：
1. 用户明确询问 "怎么从 A 到 B"、"去 X 怎么走"、"路线规划"
2. 在你推荐了多个景点 / 餐厅 / 酒店之后，如果用户表达了游览意图（"想去"、
   "推荐几个地方玩"、"周末去哪"、"帮我规划"），应主动把它们串成一条路线
3. 多日行程规划时，为每天的多个地点安排动线

**不应触发**：
- 用户只问单一信息（天气、单点开放时间、票价等）
- 用户只给目的地、没有出发地——先反问出发地，不要凭空猜测坐标

**调用参数说明**：
- `origin` / `destination` / `waypoints` 均为 `'经度,纬度'` 字符串（如 `'120.620,31.320'`）
- 优先使用你已知的著名地点常用坐标；不确定的地点宁可不传，也不要编造
- `marker_names` 强烈建议传入对应中文名称数组，让地图上有可读的标签
- `route_name` 给路线起个简洁标题（"苏州一日游"、"Day 1：古城核心区"）

### 用户体验原则

- **仅当你本轮确实调用了 `get_directions` 并成功返回了路线数据时**，才在文字回答末尾用一句简短的话告诉用户："路线已生成，点击回答下方的地图按钮即可查看完整动线"。不要重复啰嗦。
- **本轮没有调用路线工具、没有产生任何路线数据时，绝对禁止**说"地图已准备好""已为你显示地图""已把路线画在左边/右边"之类——没有就是没有，这种话会严重误导用户。这种情况下宁可完全不提地图。
- 用户通常不知道本助手能画地图。当对话涉及多地点游玩 / 行程规划、但本轮还不该出图时（例如缺出发地、信息不足），**主动、明确地告知一次这个能力和用法**："我可以把你的游览路线画到地图上——只要告诉我出发地和想去的地方，规划好后点击回答下方的地图按钮就能看到完整路线。"同一对话不要重复这句
- 你的回答风格：简洁、友好、有规划感，像一个真实的旅游顾问

## 示例

**示例 1（应调用 get_directions）**：
> 用户：苏州有什么经典景点，帮我推荐几个

正确做法：
1. 给出 3-5 个景点推荐（拙政园、狮子林、寒山寺、留园、虎丘等）及简短理由
2. 调用 `get_directions`，origin/waypoints/destination 用这些景点的常用坐标，
   `mode="driving"`，`route_name="苏州古城一日游"`
3. 文字回答末尾提示用户点击回答下方按钮查看路线地图

**示例 2（应调用 get_directions）**：
> 用户：从外滩到迪士尼怎么走？

正确做法：直接调 `get_directions`，origin=外滩坐标，destination=迪士尼坐标，
`mode="driving"`，给出文字版动线说明 + 提示点击回答下方按钮查看路线地图。

**示例 3（不应调用）**：
> 用户：今天上海天气怎么样？

只调 `get_weather`，不调路线工具。

**示例 4（先反问）**：
> 用户：我想去拙政园

回答："好的！你打算从哪里出发呢？告诉我之后我可以帮你规划路线，并提供地图按钮供你查看。"

## 行程整合与导出工作流

当你判断信息收集足够时（已经完成了天气查询、各日路线规划），按以下顺序：

1. 调用 `generate_itinerary_summary`，严格按 schema 组织数据：
   - 每天 `schedule` 按时间顺序排列；`type` 字段必须准确选 `depart` / `visit` / `meal` / `transit` / `return`
   - `day_cost` 与 `total_budget` 数字要算清楚加总
   - `important_notes` 写 3-5 条最关键的提示（不要凑数）

2. 工具返回后，**用 2-3 句话简短回答**：
   - 不要重复行程内容（用户会看到卡片）
   - 突出 1-2 个亮点
   - 引导："完整行程卡片已生成，你可以在聊天框里展开查看。需要我导出为 PDF 或 Word 保存吗？"

3. 用户要导出时调用 `export_itinerary`：
   - 默认 `format=pdf`；用户说 "Word" / "文档" 用 `docx`
   - 简短确认："PDF 已生成，下载链接已在聊天中显示。"
   - 如果用户连续两次说"导出 PDF"，**第二次直接复用**已有文件（工具内部已做幂等）

4. 错误处理：
   - 没有 `itinerary_id` 就被要求导出 → 引导用户先完成规划，不要瞎传 id
   - 工具返回错误时，把原因用人话解释给用户
""" + REALTIME_SEARCH_PROMPT_SECTION


def _deactivate_others(db: Session, model: type, active_id: int) -> None:
    db.query(model).filter(model.id != active_id).update({"is_active": False})


def ensure_defaults(db: Session) -> None:
    if db.scalar(select(LLMConfig).limit(1)) is None:
        db.add(
            LLMConfig(
                provider="Mock",
                model_name="wanderbot-mock",
                api_key="",
                base_url="",
                is_active=True,
            )
        )

    if db.scalar(select(EmbeddingConfig).limit(1)) is None:
        db.add(
            EmbeddingConfig(
                provider="hash",
                model_name="hash-384",
                api_key="",
                base_url="",
                is_active=True,
            )
        )

    if db.scalar(select(SystemPrompt).limit(1)) is None:
        db.add(
            SystemPrompt(
                name="WanderBot Default",
                content=DEFAULT_PROMPT,
                is_active=True,
            )
        )
    else:
        _ensure_prompt_section_present(db)

    # 工具按 name 唯一性补齐：现有 DB 没有这些工具时自动加上，
    # 让升级用户也能拿到新工具，但不会影响他们手工调过的现有工具配置。
    _ensure_tool_present(
        db,
        name="get_directions",
        label="Directions (Amap)",
        description=(
            "规划多个地点之间的驾车 / 步行路线，并把路线推送到用户右侧的地图区域。"
            "用户问 'A 到 B 怎么走'、推荐多个景点后串成行程、多日动线规划时使用。"
            "未配置 AMAP_KEY 时使用 mock 数据，仍可在地图上看到示意路径。"
        ),
        tool_type="amap_directions",
        config={"api_key": "", "host": ""},
    )
    _ensure_tool_present(
        db,
        name="generate_itinerary_summary",
        label="Itinerary Summary",
        description=(
            "把多轮工具收集到的天气 / 景点 / 路线整合成结构化行程，推送给前端渲染卡片，并缓存供导出。"
        ),
        tool_type="itinerary_summary",
        config={},
    )
    _ensure_tool_present(
        db,
        name="export_itinerary",
        label="Itinerary Export",
        description="把已生成的行程导出为 PDF 或 Word 文件，并通过 SSE 推送下载链接。",
        tool_type="itinerary_export",
        config={},
    )
    _ensure_tool_present(
        db,
        name="search_realtime_travel_info",
        label="Realtime Travel Search (Tavily)",
        description=REALTIME_SEARCH_DESCRIPTION,
        tool_type="tavily_realtime_search",
        config={"api_key": ""},
    )

    db.commit()


def _ensure_prompt_section_present(db: Session) -> None:
    prompts = list(db.scalars(select(SystemPrompt)).all())
    for prompt in prompts:
        if "## 实时信息搜索能力" not in (prompt.content or ""):
            prompt.content = f"{prompt.content.rstrip()}\n\n{REALTIME_SEARCH_PROMPT_SECTION.strip()}"


def _ensure_tool_present(
    db: Session,
    *,
    name: str,
    label: str,
    description: str,
    tool_type: str,
    config: dict,
    is_active: bool = True,
) -> None:
    existing = db.scalar(select(Tool).where(Tool.name == name))
    if existing is not None:
        return
    db.add(
        Tool(
            name=name,
            label=label,
            description=description,
            tool_type=tool_type,
            config=json.dumps(config, ensure_ascii=False),
            is_active=is_active,
        )
    )


def get_active_llm_config(db: Session) -> LLMConfig:
    config = db.scalar(select(LLMConfig).where(LLMConfig.is_active.is_(True)).order_by(LLMConfig.id))
    if config is None:
        ensure_defaults(db)
        config = db.scalar(select(LLMConfig).order_by(LLMConfig.id))
    return config


def get_active_embedding_config(db: Session) -> EmbeddingConfig:
    config = db.scalar(select(EmbeddingConfig).where(EmbeddingConfig.is_active.is_(True)).order_by(EmbeddingConfig.id))
    if config is None:
        ensure_defaults(db)
        config = db.scalar(select(EmbeddingConfig).order_by(EmbeddingConfig.id))
    return config


def get_active_system_prompt(db: Session) -> SystemPrompt:
    prompt = db.scalar(select(SystemPrompt).where(SystemPrompt.is_active.is_(True)).order_by(SystemPrompt.id))
    if prompt is None:
        ensure_defaults(db)
        prompt = db.scalar(select(SystemPrompt).order_by(SystemPrompt.id))
    return prompt


def list_llm_configs(db: Session) -> list[LLMConfig]:
    ensure_defaults(db)
    return list(db.scalars(select(LLMConfig).order_by(LLMConfig.id)).all())


def create_llm_config(db: Session, payload: LLMConfigCreate) -> LLMConfig:
    config = LLMConfig(**payload.model_dump())
    db.add(config)
    db.commit()
    db.refresh(config)
    if config.is_active:
        _deactivate_others(db, LLMConfig, config.id)
        db.commit()
        db.refresh(config)
    return config


def update_llm_config(db: Session, config_id: int, payload: LLMConfigUpdate) -> Optional[LLMConfig]:
    config = db.get(LLMConfig, config_id)
    if config is None:
        return None

    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "api_key" and is_masked_secret(value):
            continue
        setattr(config, key, value)

    db.commit()
    db.refresh(config)
    if config.is_active:
        _deactivate_others(db, LLMConfig, config.id)
        db.commit()
        db.refresh(config)
    return config


def delete_llm_config(db: Session, config_id: int) -> bool:
    config = db.get(LLMConfig, config_id)
    if config is None:
        return False
    db.delete(config)
    db.commit()
    ensure_defaults(db)
    return True


def list_embedding_configs(db: Session) -> list[EmbeddingConfig]:
    ensure_defaults(db)
    return list(db.scalars(select(EmbeddingConfig).order_by(EmbeddingConfig.id)).all())


def create_embedding_config(db: Session, payload: EmbeddingConfigCreate) -> EmbeddingConfig:
    config = EmbeddingConfig(**payload.model_dump())
    db.add(config)
    db.commit()
    db.refresh(config)
    if config.is_active:
        _deactivate_others(db, EmbeddingConfig, config.id)
        db.commit()
        db.refresh(config)
    return config


def update_embedding_config(db: Session, config_id: int, payload: EmbeddingConfigUpdate) -> Optional[EmbeddingConfig]:
    config = db.get(EmbeddingConfig, config_id)
    if config is None:
        return None

    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "api_key" and is_masked_secret(value):
            continue
        setattr(config, key, value)

    db.commit()
    db.refresh(config)
    if config.is_active:
        _deactivate_others(db, EmbeddingConfig, config.id)
        db.commit()
        db.refresh(config)
    return config


def delete_embedding_config(db: Session, config_id: int) -> bool:
    config = db.get(EmbeddingConfig, config_id)
    if config is None:
        return False
    db.delete(config)
    db.commit()
    ensure_defaults(db)
    return True


def list_system_prompts(db: Session) -> list[SystemPrompt]:
    ensure_defaults(db)
    return list(db.scalars(select(SystemPrompt).order_by(SystemPrompt.id)).all())


def create_system_prompt(db: Session, payload: SystemPromptCreate) -> SystemPrompt:
    data = payload.model_dump()
    data["knowledge_scope"] = json.dumps(data.get("knowledge_scope") or [], ensure_ascii=False)
    prompt = SystemPrompt(**data)
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    if prompt.is_active:
        _deactivate_others(db, SystemPrompt, prompt.id)
        db.commit()
        db.refresh(prompt)
    return prompt


def update_system_prompt(db: Session, prompt_id: int, payload) -> Optional[SystemPrompt]:
    prompt = db.get(SystemPrompt, prompt_id)
    if prompt is None:
        return None

    data = payload.model_dump(exclude_unset=True)
    if "knowledge_scope" in data:
        data["knowledge_scope"] = json.dumps(data.get("knowledge_scope") or [], ensure_ascii=False)
    for key, value in data.items():
        setattr(prompt, key, value)

    db.commit()
    db.refresh(prompt)
    if prompt.is_active:
        _deactivate_others(db, SystemPrompt, prompt.id)
        db.commit()
        db.refresh(prompt)
    return prompt


def delete_system_prompt(db: Session, prompt_id: int) -> bool:
    prompt = db.get(SystemPrompt, prompt_id)
    if prompt is None:
        return False
    db.delete(prompt)
    db.commit()
    ensure_defaults(db)
    return True


def update_active_admin_config(db: Session, payload: AdminConfigUpdate) -> tuple[LLMConfig, SystemPrompt]:
    llm_config = get_active_llm_config(db)
    system_prompt = get_active_system_prompt(db)

    for key, value in payload.llm_config.model_dump(exclude_unset=True).items():
        if key == "api_key" and is_masked_secret(value):
            continue
        setattr(llm_config, key, value)
    llm_config.is_active = True

    system_prompt_data = payload.system_prompt.model_dump(exclude_unset=True)
    if "knowledge_scope" in system_prompt_data:
        system_prompt_data["knowledge_scope"] = json.dumps(
            system_prompt_data.get("knowledge_scope") or [], ensure_ascii=False
        )
    for key, value in system_prompt_data.items():
        setattr(system_prompt, key, value)
    system_prompt.is_active = True

    db.commit()
    db.refresh(llm_config)
    db.refresh(system_prompt)
    return llm_config, system_prompt
