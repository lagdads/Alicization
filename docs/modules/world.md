文件职责：描述 World 模块的目录结构与文件职责。
简明实现逻辑：以 ECS 组合对象，维护世界状态并推进时间/规则。
输入输出：输入为世界层配置与实体状态；输出为行动结算与世界状态。

# World 模块结构

```
src/world/
├── __init__.py
├── environment.py  # 环境状态与时间推进
├── map.py          # 2D 地图矩阵与地形类型
├── object.py       # Object 与组件定义（ECS 组合）
└── survival_war.py # 生存战争世界会话与规则
```

## 关键职责

- `environment.py`: 维护环境状态、实体集合与时间步进
- `map.py`: 管理世界 2D 矩阵与地形查询
- `object.py`: Object 抽象与组件化能力（组合优于继承）
- `survival_war.py`: 生存战争会话（地图/NPC/武器刷新/行动结算/胜负判定）

## 核心逻辑说明

### ECS 组合设计（大于继承）

- 世界对象统一为 `Object`（包含普通物体与 NPC）
- 通过组件组合能力而非继承：
  - `Position`: 世界坐标
  - `Destiny`: 天命值，归零即消失/死亡
  - `Holdable`: 可持有接口与持有等级
  - `HolderPermission`: NPC 的持有权限等级
  - `AccessPermission`: NPC 的访问权限等级（限制系统指令）

### Object 规则

- 所有物体（含 NPC）拥有天命值，天命值归零即从世界移除
- 可持有物体带有持有等级，NPC 只有在持有权限等级高于物体要求时可拿起并使用
- NPC 访问权限等级限制可使用的系统指令范围

### 世界结构

- 世界为 2D 矩阵，中心点坐标为 `(0, 0)`
- 每个格点地形类型为陆地或海洋
- Object 必须绑定世界坐标

### 时间与 Tick

- `Environment`：一天 5 个 tick；每个 tick NPC 可执行 1 次行动；日终触发记忆整理并输出提示
- `SurvivalWarSession`：按 `tick_count` 推进；每 tick 存活 NPC 执行 1 次行动；满足胜负条件后结束并进入赛后对话

### 生存战争会话

- 维护 NPC 状态（位置/天命/武器/存活）
- 处理武器刷新与拾取
- 支持观察附近 NPC 的行动反馈
- 判定胜负并触发赛后对话

### 多世界观数据

- 世界目录：`data/worlds/<world_id>/`
- 世界配置：`data/worlds/<world_id>/world_config.toml`
- 世界观：`data/worlds/<world_id>/world_lore.toml`
- 人设与记忆目录：`data/worlds/<world_id>/personas/`、`memory/`、`knowledge/`、`saves/`
- Git 版本管理：建议仅提交 `memory/**.core.json`；其余 `memory/`、`knowledge/`、`saves/` 为运行产物

### 状态说明

- `SurvivalWarSession` 已接入 CLI 运行流程；`Environment` 仍为基础容器与拓展位。
