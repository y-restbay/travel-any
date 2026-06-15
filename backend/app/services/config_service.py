import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import EmbeddingConfig, LLMConfig, SystemPrompt, Tool, VLMConfig
from app.schemas.config import (
    AdminConfigUpdate,
    EmbeddingConfigCreate,
    EmbeddingConfigUpdate,
    LLMConfigCreate,
    LLMConfigUpdate,
    SystemPromptCreate,
    VLMConfigCreate,
    VLMConfigUpdate,
    is_masked_secret,
)
from app.travel_tools.landmark_tool import LANDMARK_TOOL_DESCRIPTION
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

LANDMARK_PROMPT_SECTION = """
## 图片识别与多模态交互

你具备识别用户上传图片中景点地标的能力(通过 identify_landmark 工具)。

### 如何感知图片
当用户消息包含 [图片 image_ref=xxx] 或 [图片 image_refs=a,b,c] 标记时,表示用户上传了图片。
你应针对每个 image_ref 调用 identify_landmark 进行识别。
注意:你本身看不到图片内容,必须通过 identify_landmark 工具获取识别结果。

### 识别后的处理:identify_landmark 只是第一步
识别工具返回景点名后,把它当作"已知事实",再根据用户的真实需求
继续调用其他工具。识别本身不是终点,而是后续服务的起点。

**关键**:一旦识别出景点名,后续处理与"用户用文字提到这个景点"完全一样。
- 用户要周边美食 → search_places
- 用户要规划行程 → get_directions + generate_itinerary_summary
- 用户问最新动态 → search_realtime_travel_info
- 用户要天气 → get_weather

### 场景一:图 + 明确问题
先识别,再根据问题调用对应工具,综合回答。
例:发拙政园图问"附近吃什么" → identify_landmark → search_places → 回答

### 场景二:图 + 规划需求(重要,体现工具串联)
例:发拙政园图说"基于这里帮我规划一天"
→ identify_landmark 识别出拙政园
→ 把拙政园作为行程起点,search_places 查周边景点
→ get_weather 查天气
→ get_directions 规划路线
→ generate_itinerary_summary 整合一日游
→ 完整回答 + 地图 + 行程卡片
这与用户打字"基于拙政园规划一天"的处理完全一致。

### 场景三:图 + 模糊问题
"这个怎么样""值得去吗" → 识别后主动提供介绍、亮点,
适当延展(周边/交通),引导用户说明具体需求。

### 场景四:只有图,没有任何文字(重点)
用户拍照发来说明对此地感兴趣。回答遵循以下结构:
1. 确认识别结果(让用户确认你识别正确)
2. 主动提供核心介绍(1-3 句)
3. 轻量延展(2-3 个可选方向:周边美食/路线/附近景点)
4. 开放引导(询问用户是已在当地还是规划行程)

### 场景五:多张图片
- **对比类**("这几个哪个值得去"):逐一调用 identify_landmark 识别每张,
  然后对比介绍各景点特色,给出建议
- **组合规划类**("我想去这几个地方"):全部识别后,串成一条游览路线,
  调用 get_directions + generate_itinerary_summary 规划
- **多图无文字**:逐一识别并简要介绍每个,询问用户重点关注哪个或想如何安排

### 场景六:识别不确定/失败
绝不编造景点名。描述图片特征,礼貌询问城市或名称缩小范围。

### 场景七:图片主要是人物
返回 is_person_focused 时,礼貌说明只识别景点,请用户发景点照片。

### 核心原则
1. 主动但不过度:无文字时也主动给价值,但不要一次堆砌所有信息
2. 始终先确认识别结果,给用户纠错机会
3. 诚实优先:不确定就说不确定,绝不用错误肯定误导
4. 引导自然多变,根据景点类型调整措辞,避免模板感
5. 不忽略图片:有图必回应图,不能只回应文字
6. 隐私:只识别景点地标,不识别图中人物身份
"""

EXPORT_CHAIN_PROMPT_SECTION = """
## 连续导出动作规则

当用户在同一句话里同时要求“总结 / 整理 / 生成卡片”和“生成 PDF / 导出 PDF / 保存成 Word / 下载文档”时，必须在同一轮连续完成，不要只总结后再问用户是否导出。

执行顺序：
1. 如果上文已有完整行程卡片，直接调用 `export_itinerary(format="pdf")` 或 `export_itinerary(format="docx")`。
2. 如果上文还没有行程卡片但已有完整行程内容，先调用 `generate_itinerary_summary` 生成卡片，再立即调用 `export_itinerary(itinerary_id=刚返回的id, format="pdf")`。
3. 如果不知道 `itinerary_id` 但用户说的是“当前 / 上面 / 刚才这份行程”，也要调用 `export_itinerary(format="pdf")`；系统会自动导出最近生成的行程。
4. 最终只简短确认下载链接已显示，不要重复整份行程。

Few-shot：
用户：“帮我总结一下，并生成 PDF。”
正确动作：生成或复用行程卡片 → 立即调用 `export_itinerary(format="pdf")` → 回复“已整理完成，PDF 下载链接已显示在聊天中。”
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
   - 如果用户没有要求导出，引导："完整行程卡片已生成，你可以在聊天框里展开查看。需要我导出为 PDF 或 Word 保存吗？"
   - 如果用户本轮已经说了"生成 PDF / 导出 PDF / 保存成 Word / 总结并生成 PDF"，不要再询问，继续执行第 3 步

3. 用户要导出时调用 `export_itinerary`：
   - 默认 `format=pdf`；用户说 "Word" / "文档" 用 `docx`
   - 如果刚刚调用过 `generate_itinerary_summary`，优先使用工具返回的 `itinerary_id`
   - 如果用户说"导出当前/上面/刚才这份行程"但你不知道 `itinerary_id`，也要调用 `export_itinerary(format="pdf")`，系统会自动导出最近行程
   - 简短确认："PDF 已生成，下载链接已在聊天中显示。"
   - 如果用户连续两次说"导出 PDF"，**第二次直接复用**已有文件（工具内部已做幂等）

4. 错误处理：
   - 没有任何已生成行程又被要求导出 → 先调用 `generate_itinerary_summary` 生成行程卡片；如果信息不足，再追问关键缺口
   - 工具返回错误时，把原因用人话解释给用户

### 连续动作 few-shot

**示例 5（总结并导出，必须连续调用两个工具）**：
> 用户：帮我把上面的 5 天游总结一下，并生成 PDF

正确做法：
1. 如果上文已有完整行程卡片，直接调用 `export_itinerary(format="pdf")`，不要要求用户再说一遍。
2. 如果上文还没有卡片但已经有完整行程内容，先调用 `generate_itinerary_summary` 生成卡片，再立即调用 `export_itinerary(itinerary_id=刚返回的id, format="pdf")`。
3. 最终只用 1-2 句话确认："已整理成可保存版本，PDF 已生成，下载链接已显示在聊天中。"
""" + EXPORT_CHAIN_PROMPT_SECTION + REALTIME_SEARCH_PROMPT_SECTION + LANDMARK_PROMPT_SECTION


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

    if db.scalar(select(VLMConfig).limit(1)) is None:
        db.add(
            VLMConfig(
                provider="dashscope",
                model_name="qwen3.6-flash",
                api_key="",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
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
        name="get_weather",
        label="Weather (QWeather)",
        description=(
            "查询任意城市的实时天气或未来 3/7 天天气预报，可选生活指数与逐小时数据。"
            "用户询问某地天气、是否下雨、穿衣建议、出行天气、紫外线、台风预警等情况时使用。"
            "默认从服务器环境变量 QWEATHER_KEY / QWEATHER_HOST / QWEATHER_GEO_HOST 读取配置。"
        ),
        tool_type="qweather_weather",
        config={"api_key": "", "weather_host": "", "geo_host": ""},
    )
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
    _ensure_tool_present(
        db,
        name="identify_landmark",
        label="Identify Landmark (VLM)",
        description=LANDMARK_TOOL_DESCRIPTION,
        tool_type="landmark_identify",
        # 留空表示从 vlm_configs 活跃配置读取;再缺则回退 DASHSCOPE_API_KEY 环境变量
        config={"model": "", "base_url": "", "api_key": ""},
    )

    db.commit()


def _ensure_prompt_section_present(db: Session) -> None:
    prompts = list(db.scalars(select(SystemPrompt)).all())
    for prompt in prompts:
        if "## 连续导出动作规则" not in (prompt.content or ""):
            prompt.content = f"{prompt.content.rstrip()}\n\n{EXPORT_CHAIN_PROMPT_SECTION.strip()}"
        if "## 实时信息搜索能力" not in (prompt.content or ""):
            prompt.content = f"{prompt.content.rstrip()}\n\n{REALTIME_SEARCH_PROMPT_SECTION.strip()}"
        # 图片识别 section 迁移：旧版标题替换为新版完整内容
        old_landmark_header = "## 图片识别景点工作流（看图识景点）"
        if old_landmark_header in (prompt.content or ""):
            # 从旧版标题到下一个 ## 之间的内容全部替换
            import re
            prompt.content = re.sub(
                rf"{re.escape(old_landmark_header)}.*?(?=\n## |\Z)",
                LANDMARK_PROMPT_SECTION.strip(),
                prompt.content,
                flags=re.DOTALL,
            )
        elif "## 图片识别与多模态交互" not in (prompt.content or ""):
            prompt.content = f"{prompt.content.rstrip()}\n\n{LANDMARK_PROMPT_SECTION.strip()}"


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


def get_active_vlm_config(db: Session) -> Optional[VLMConfig]:
    """读取当前活跃的 VLM(图片识别)配置;没有则返回 None,让客户端走环境变量。"""
    config = db.scalar(select(VLMConfig).where(VLMConfig.is_active.is_(True)).order_by(VLMConfig.id))
    if config is None:
        config = db.scalar(select(VLMConfig).order_by(VLMConfig.id))
    return config


def list_vlm_configs(db: Session) -> list[VLMConfig]:
    ensure_defaults(db)
    return list(db.scalars(select(VLMConfig).order_by(VLMConfig.id)).all())


def create_vlm_config(db: Session, payload: VLMConfigCreate) -> VLMConfig:
    config = VLMConfig(**payload.model_dump())
    db.add(config)
    db.commit()
    db.refresh(config)
    if config.is_active:
        _deactivate_others(db, VLMConfig, config.id)
        db.commit()
        db.refresh(config)
    return config


def update_vlm_config(db: Session, config_id: int, payload: VLMConfigUpdate) -> Optional[VLMConfig]:
    config = db.get(VLMConfig, config_id)
    if config is None:
        return None

    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "api_key" and is_masked_secret(value):
            continue
        setattr(config, key, value)

    db.commit()
    db.refresh(config)
    if config.is_active:
        _deactivate_others(db, VLMConfig, config.id)
        db.commit()
        db.refresh(config)
    return config


def delete_vlm_config(db: Session, config_id: int) -> bool:
    config = db.get(VLMConfig, config_id)
    if config is None:
        return False
    db.delete(config)
    db.commit()
    ensure_defaults(db)
    return True


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
