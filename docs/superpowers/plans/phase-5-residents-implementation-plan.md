# Phase 5 实施计划 - Residents 居民系统

**目标**：实现居民聚合根数据模型和基础生命周期管理

**预计时间**：4-5 天  
**当前状态**：规划中

---

## 一、实施策略

采用**分层渐进式实现**：
1. 先实现核心数据模型（Aggregate Schema）
2. 再实现各子系统（Identity、Personality、Needs、Health 等）
3. 最后实现生命周期管理和初始化

---

## 二、实施步骤

### Step 1: 基础设施准备（0.5天）
- [ ] 创建 `backend/src/residents/` 模块结构
- [ ] 定义 Resident Aggregate Schema（Pydantic 模型）
- [ ] 实现 ResidentRepository（内存存储 + SQLite 持久化接口）
- [ ] 编写基础单元测试

**交付物**：
- `residents/__init__.py`
- `residents/models.py` - Pydantic 数据模型
- `residents/repository.py` - Repository 接口
- `residents/schemas.py` - Schema 版本定义

---

### Step 2: Identity 身份系统（0.5天）
**对应文档**：DOC-RESIDENT-002

- [ ] ResidentIdentity 数据模型
  - display_name, self_name, pronoun_id
  - ancestry_id, culture_ids
  - language_proficiencies
  - appearance (sprite_asset_id, portrait_asset_id)
- [ ] 身份验证逻辑
- [ ] 单元测试

**交付物**：
- `residents/identity.py`

---

### Step 3: Personality 个性系统（0.5天）
**对应文档**：DOC-RESIDENT-003

- [ ] ResidentPersonality 数据模型
  - dimensions (6维度：sociability, diligence, curiosity, empathy, caution, assertiveness)
  - values (价值观列表)
  - preferences (偏好列表)
  - fears (恐惧列表)
- [ ] 个性生成逻辑（随机 + 种子）
- [ ] 单元测试

**交付物**：
- `residents/personality.py`

---

### Step 4: Needs & Emotions 需求与情绪（1天）
**对应文档**：DOC-RESIDENT-004

- [ ] ResidentNeedsState 数据模型
  - hunger, fatigue, safety, social, comfort (0-1000 量化值)
  - last_updated_game_time
- [ ] Emotion 情绪模型
  - primary emotion, intensity, cause_event_ids
  - decay_rate (情绪衰减速率)
- [ ] 需求衰减逻辑（按游戏时间）
- [ ] 情绪计算和更新
- [ ] 单元测试

**交付物**：
- `residents/needs.py`
- `residents/emotions.py`

---

### Step 5: Capability 技能能力（0.5天）
**对应文档**：DOC-RESIDENT-005

- [ ] ResidentCapabilityState 数据模型
  - skills (技能评级 + XP)
  - ability_ids (已解锁能力列表)
  - last_practiced_game_time
- [ ] 技能成长逻辑
- [ ] 单元测试

**交付物**：
- `residents/capability.py`

---

### Step 6: Assignment 职业与住所（0.5天）
**对应文档**：DOC-RESIDENT-006

- [ ] ResidentAssignmentState 数据模型
  - profession (职业分配：profession_id, workplace_id, state)
  - residence (住所分配：building_id, interior_scene_id, bed_node_id)
  - effective_from/until_game_time
- [ ] 分配验证逻辑
- [ ] 单元测试

**交付物**：
- `residents/assignment.py`

---

### Step 7: Health 健康状态（0.5天）
**对应文档**：DOC-RESIDENT-007

- [ ] ResidentHealthState 数据模型
  - condition (healthy, injured, ill, critical)
  - hp_current, hp_max
  - injuries (伤势列表)
  - illnesses (疾病列表)
  - restrictions (行动限制)
- [ ] 健康状态更新逻辑
- [ ] 单元测试

**交付物**：
- `residents/health.py`

---

### Step 8: Lifecycle 生命周期（0.5天）
**对应文档**：DOC-RESIDENT-008

- [ ] ResidentLifecycle 数据模型
  - age_stage (child, teen, adult, elder)
  - lifecycle_state (active, downed, inactive)
  - defeat (非永久死亡记录)
- [ ] 生命周期状态机
- [ ] 非永久死亡机制
- [ ] 单元测试

**交付物**：
- `residents/lifecycle.py`

---

### Step 9: Routine 日常作息（0.5天）
**对应文档**：DOC-RESIDENT-009

- [ ] ResidentRoutineState 数据模型
  - schedule_profile_id
  - windows (作息窗口列表)
    - window_id, day_type
    - start_minute_of_day, end_minute_of_day
    - candidate_activity_tags
    - preferred_destination_ids
    - flexibility, interruptibility
  - active_long_action_id
- [ ] 作息匹配逻辑
- [ ] 单元测试

**交付物**：
- `residents/routine.py`

---

### Step 10: Resident 聚合根整合（0.5天）

- [ ] 整合所有子系统到 ResidentAggregate
- [ ] 实现完整的 CRUD 操作
- [ ] 实现 ResidentSummaryProjection（只读摘要）
- [ ] 版本管理（resident_revision）
- [ ] 集成测试

**交付物**：
- `residents/aggregate.py`
- 更新 `residents/repository.py`

---

### Step 11: Resident 创建与初始化（1天）
**对应文档**：DOC-RESIDENT-011

- [ ] ResidentFactory 工厂类
- [ ] 从 resident_key 创建居民
- [ ] 从配置文件批量创建初始居民
- [ ] 为10个角色创建初始数据
  - human_farmer
  - elf_mage
  - dwarf_blacksmith
  - halfling_merchant
  - human_guard
  - human_priest
  - human_innkeeper
  - elf_alchemist
  - human_hunter
  - dwarf_miner
- [ ] 单元测试

**交付物**：
- `residents/factory.py`
- `data/residents/initial_residents.json` - 初始居民配置

---

### Step 12: REST API 接口（0.5天）

- [ ] GET /api/residents - 获取居民列表
- [ ] GET /api/residents/{resident_id} - 获取单个居民详情
- [ ] GET /api/residents/{resident_id}/summary - 获取居民摘要
- [ ] POST /api/residents - 创建新居民（测试用）
- [ ] 集成到 FastAPI main.py

**交付物**：
- `backend/src/api/residents.py`
- 更新 `backend/src/main.py`

---

### Step 13: 前端集成（0.5天）

- [ ] 创建 ResidentInfo UI 组件
- [ ] 显示居民基本信息（名字、种族、职业）
- [ ] 显示需求条（hunger, fatigue, social 等）
- [ ] 显示情绪状态
- [ ] 显示健康状态
- [ ] 点击角色显示详情面板

**交付物**：
- `frontend/src/ui/ResidentInfoPanel.ts`
- `frontend/src/types/resident.ts`
- 更新 `frontend/src/scenes/WorldScene.ts`

---

### Step 14: 验收测试（0.5天）

- [ ] 编写完整的集成测试
- [ ] 验证所有数据模型符合文档规范
- [ ] 验证 API 端点正常工作
- [ ] 验证前端显示正确
- [ ] 性能测试（100个居民）
- [ ] 编写验收报告

**交付物**：
- `backend/tests/test_residents_integration.py`
- `docs/superpowers/reports/phase-5-acceptance.md`

---

## 三、技术要点

### 数据建模
- 使用 Pydantic V2 进行数据验证
- 所有量化值使用 `q1000` 格式（0-1000 整数）
- 使用 ULID 作为 ID 格式
- Schema 版本化管理

### 持久化
- 内存存储：Dict[resident_id, ResidentAggregate]
- SQLite 持久化：JSON 序列化存储
- 支持快照和增量更新

### 前后端通信
- 后端：FastAPI + Pydantic 自动生成 JSON Schema
- 前端：TypeScript 类型定义
- WebSocket：实时状态更新（后续实现）

---

## 四、依赖文档

- ✅ DOC-FOUNDATION-003: 系统边界与依赖
- ✅ DOC-FOUNDATION-005: 跨系统不变量
- ✅ DOC-FOUNDATION-006: ID、时间、坐标标准
- 📖 DOC-RESIDENT-001: 居民聚合与数据模型
- 📖 DOC-RESIDENT-002: 身份、种族与外观
- 📖 DOC-RESIDENT-003: 个性与价值观
- 📖 DOC-RESIDENT-004: 需求与情绪
- 📖 DOC-RESIDENT-005: 技能与能力
- 📖 DOC-RESIDENT-006: 职业与住所
- 📖 DOC-RESIDENT-007: 健康、受伤与疾病
- 📖 DOC-RESIDENT-008: 年龄与非永久死亡
- 📖 DOC-RESIDENT-009: 日常生活结构
- 📖 DOC-RESIDENT-011: 居民创建与初始化

---

## 五、验收标准

### 功能验收
- [ ] 后端能创建和存储居民数据
- [ ] 所有子系统数据模型完整
- [ ] 10个初始居民成功创建
- [ ] API 接口正常工作
- [ ] 前端能显示居民信息和状态

### 质量验收
- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 集成测试通过
- [ ] 符合所有 RULE-RESIDENT-* 规范
- [ ] 代码通过 Black + MyPy 检查
- [ ] 前端通过 ESLint + TypeScript 编译

### 性能验收
- [ ] 支持至少 100 个居民
- [ ] API 响应时间 < 100ms
- [ ] 内存占用合理（< 100MB for 100 residents）

---

## 六、风险与应对

| 风险 | 影响 | 应对措施 |
|---|---|---|
| 数据模型复杂度高 | 实现时间延长 | 分层实现，先核心后扩展 |
| Schema 版本管理困难 | 持久化兼容性问题 | 使用 Pydantic 严格验证 |
| 前后端类型不一致 | 通信错误 | 从 Pydantic 自动生成 TS 类型 |
| 性能问题 | 卡顿 | 使用索引、缓存、分页 |

---

## 七、下一步行动

**立即开始 Step 1: 基础设施准备**

1. 创建 `backend/src/residents/` 模块结构
2. 定义 Resident Aggregate Schema
3. 实现 Repository 接口
4. 编写基础测试

预计完成时间：0.5天（约4小时）
