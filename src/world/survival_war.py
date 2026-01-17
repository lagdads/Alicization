"""文件职责：生存战争世界会话与规则处理。
简明实现逻辑：维护 NPC/武器/地图状态，按 tick 执行行动并判定胜负。
输入输出：输入为配置与动作；输出为行动结果与赛局状态。"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import random
from typing import Dict, List, Optional, Tuple

from src.behavior.actions import Action, ActionResult
from src.world.map import WorldMap


@dataclass(frozen=True)
class WeaponSpec:
    """武器规格定义。"""

    weapon_id: str
    name: str
    damage: int
    range: int
    required_level: int


@dataclass
class WeaponInstance:
    """地图上的武器实例。"""

    instance_id: str
    spec: WeaponSpec
    position: Tuple[int, int]


@dataclass
class NPCState:
    """生存战争 NPC 状态。"""

    npc_id: str
    name: str
    position: Tuple[int, int]
    destiny: float
    holder_level: int
    alive: bool = True
    weapon: Optional[WeaponSpec] = None


@dataclass
class SessionActionOutcome:
    """单次行动执行结果。"""

    npc_id: str
    action: Action
    result: ActionResult


class SurvivalWarSession:
    """生存战争世界会话与战斗规则。"""

    DEFAULT_MAP_SIZE = (9, 9)
    DEFAULT_DESTINY = 10.0
    DEFAULT_HOLDER_LEVEL = 1
    DEFAULT_BASE_DAMAGE = 1

    def __init__(
        self,
        world_map: WorldMap,
        npcs: Dict[str, NPCState],
        weapon_pool: List[WeaponSpec],
        max_weapons: int,
        spawn_interval_ticks: int,
        spawn_chance: float,
        base_damage: int,
        observe_radius: int,
        rng: random.Random,
        logger: logging.Logger,
    ) -> None:
        """初始化会话状态。"""
        self.world_map = world_map
        self.npcs = npcs
        self.weapon_pool = weapon_pool
        self.max_weapons = max(0, max_weapons)
        self.spawn_interval_ticks = max(1, spawn_interval_ticks)
        self.spawn_chance = min(1.0, max(0.0, spawn_chance))
        self.base_damage = max(0, base_damage)
        self.observe_radius = max(0, observe_radius)
        self.rng = rng
        self.logger = logger
        self.tick_count = 0
        self.weapons: Dict[str, WeaponInstance] = {}
        self._weapon_counter = 0
        self.event_log: List[str] = []
        self.game_over = False
        self.winner_id: Optional[str] = None

    @classmethod
    def from_config(
        cls,
        config: Dict[str, object],
        base_dir: Optional[object] = None,
        logger: Optional[logging.Logger] = None,
    ) -> "SurvivalWarSession":
        """从世界配置创建生存战争会话。"""
        logger = logger or logging.getLogger("alicization.survival_war")
        map_cfg = config.get("map", {}) if isinstance(config.get("map"), dict) else {}
        width = int(map_cfg.get("width", cls.DEFAULT_MAP_SIZE[0]))
        height = int(map_cfg.get("height", cls.DEFAULT_MAP_SIZE[1]))
        world_map = WorldMap(width=width, height=height)

        spawn_cfg = (
            config.get("spawn", {}) if isinstance(config.get("spawn"), dict) else {}
        )
        max_weapons = int(spawn_cfg.get("max_weapons", 3))
        spawn_interval = int(spawn_cfg.get("spawn_interval_ticks", 2))
        spawn_chance = float(spawn_cfg.get("spawn_chance", 0.6))
        seed = spawn_cfg.get("seed")
        rng = random.Random(seed)

        combat_cfg = (
            config.get("combat", {}) if isinstance(config.get("combat"), dict) else {}
        )
        base_damage = int(combat_cfg.get("base_damage", cls.DEFAULT_BASE_DAMAGE))
        observe_radius = int(combat_cfg.get("observe_radius", 3))

        weapon_pool = _parse_weapon_pool(config.get("weapons"), logger)
        npcs = _parse_npcs(config.get("npcs"), world_map, rng, logger)

        session = cls(
            world_map=world_map,
            npcs=npcs,
            weapon_pool=weapon_pool,
            max_weapons=max_weapons,
            spawn_interval_ticks=spawn_interval,
            spawn_chance=spawn_chance,
            base_damage=base_damage,
            observe_radius=observe_radius,
            rng=rng,
            logger=logger,
        )
        return session

    def npc_ids(self) -> List[str]:
        """返回 NPC ID 列表。"""
        return list(self.npcs.keys())

    def snapshot_state(self, npc_id: str) -> Dict[str, object]:
        """生成 NPC 的可视状态快照。"""
        npc = self.npcs[npc_id]
        return {
            "position": {"x": npc.position[0], "y": npc.position[1]},
            "destiny": npc.destiny,
            "alive": npc.alive,
            "weapon": npc.weapon.name if npc.weapon else None,
            "weapon_damage": npc.weapon.damage if npc.weapon else 0,
            "weapon_range": npc.weapon.range if npc.weapon else 1,
            "game_over": self.game_over,
            "winner": self.winner_id,
        }

    def step(self) -> List[SessionActionOutcome]:
        """推进一个 tick，执行 NPC 行动并返回结果。"""
        if self.game_over:
            return []
        self.tick_count += 1
        self._spawn_weapon_if_needed()
        outcomes: List[SessionActionOutcome] = []
        for npc_id in list(self.npcs.keys()):
            npc = self.npcs[npc_id]
            if not npc.alive:
                continue
            action = self._decide_action(npc)
            result = self.execute_action(npc_id, action)
            outcomes.append(SessionActionOutcome(npc_id=npc_id, action=action, result=result))
        self._update_game_over()
        return outcomes

    def begin_tick(self) -> None:
        """开始一个 tick，用于刷新与计时。"""
        if self.game_over:
            return
        self.tick_count += 1
        self._spawn_weapon_if_needed()

    def end_tick(self) -> None:
        """结束一个 tick 并更新胜负状态。"""
        self._update_game_over()

    def nearest_enemy_id(self, npc_id: str) -> Optional[str]:
        """获取最近敌对 NPC 的 ID。"""
        npc = self.npcs.get(npc_id)
        if not npc:
            return None
        enemy = self._nearest_enemy(npc)
        return enemy.npc_id if enemy else None

    def summary(self, max_events: int = 12) -> str:
        """输出赛局摘要文本。"""
        if not self.event_log:
            return "本局未产生显著事件。"
        events = self.event_log[-max_events:]
        return " | ".join(events)

    def execute_action(self, npc_id: str, action: Action) -> ActionResult:
        """执行动作并更新会话状态。"""
        npc = self.npcs.get(npc_id)
        if not npc or not npc.alive:
            return ActionResult(False, {"error": "npc_not_alive"})
        if action.name == "move_to":
            target = (int(action.params.get("x", 0)), int(action.params.get("y", 0)))
            new_pos = self._step_toward(npc.position, target)
            npc.position = new_pos
            return ActionResult(True, {"position": {"x": new_pos[0], "y": new_pos[1]}})
        if action.name == "move":
            dx = int(action.params.get("dx", 0))
            dy = int(action.params.get("dy", 0))
            if abs(dx) + abs(dy) != 1:
                return ActionResult(False, {"error": "invalid_step"})
            new_pos = (npc.position[0] + dx, npc.position[1] + dy)
            if not _in_bounds(self.world_map, new_pos[0], new_pos[1]):
                return ActionResult(False, {"error": "out_of_bounds"})
            npc.position = new_pos
            return ActionResult(True, {"position": {"x": new_pos[0], "y": new_pos[1]}})
        if action.name == "pickup":
            weapon = self._weapon_at_position(npc.position)
            if not weapon:
                return ActionResult(False, {"error": "no_weapon_here"})
            if npc.weapon is not None:
                return ActionResult(False, {"error": "already_armed"})
            if npc.holder_level < weapon.spec.required_level:
                return ActionResult(False, {"error": "permission_denied"})
            npc.weapon = weapon.spec
            self.weapons.pop(weapon.instance_id, None)
            self._log_event(f"{npc.name} 拾取了 {weapon.spec.name}")
            return ActionResult(True, {"weapon": weapon.spec.name})
        if action.name == "attack":
            target_id = str(action.params.get("target_id", ""))
            target = self.npcs.get(target_id)
            if not target or not target.alive:
                return ActionResult(False, {"error": "target_invalid"})
            distance = _manhattan(npc.position, target.position)
            attack_range = npc.weapon.range if npc.weapon else 1
            if distance > attack_range:
                return ActionResult(False, {"error": "out_of_range", "distance": distance})
            damage = self.base_damage + (npc.weapon.damage if npc.weapon else 0)
            target.destiny -= damage
            info = {
                "target": target.name,
                "damage": damage,
                "target_destiny": max(0.0, target.destiny),
            }
            if target.destiny <= 0:
                target.alive = False
                info["killed"] = True
                self._log_event(f"{npc.name} 击败了 {target.name}")
            else:
                self._log_event(f"{npc.name} 攻击了 {target.name}，造成 {damage} 伤害")
            return ActionResult(True, info)
        if action.name == "observe_nearby_npcs":
            radius = int(action.params.get("radius", self.observe_radius))
            observations = self._observe_nearby(npc_id, radius)
            return ActionResult(True, {"radius": radius, "observations": observations})
        if action.name == "scan_nearby":
            tag = str(action.params.get("tag", "")).lower()
            if tag in ("weapon", "item"):
                weapons = self._nearby_weapons(npc.position, radius=2)
                return ActionResult(True, {"weapons": weapons})
            return ActionResult(True, {"observation": f"附近未发现 {tag}"})
        if action.name == "wait":
            return ActionResult(True, {"waited": int(action.params.get("ticks", 1))})
        return ActionResult(False, {"error": "unsupported_action"})

    def _decide_action(self, npc: NPCState) -> Action:
        """生成简单策略动作。"""
        target = self._nearest_enemy(npc)
        if target:
            distance = _manhattan(npc.position, target.position)
            attack_range = npc.weapon.range if npc.weapon else 1
            if distance <= attack_range:
                return Action(name="attack", params={"target_id": target.npc_id})
        if npc.weapon is None:
            weapon = self._weapon_at_position(npc.position)
            if weapon:
                return Action(name="pickup", params={"object_id": weapon.instance_id})
            if not self.weapons and self.observe_radius > 0:
                return Action(name="observe_nearby_npcs", params={"radius": self.observe_radius})
            nearest_weapon = self._nearest_weapon(npc.position)
            if nearest_weapon:
                return Action(
                    name="move_to",
                    params={"x": nearest_weapon.position[0], "y": nearest_weapon.position[1]},
                )
        if target:
            return Action(
                name="move_to",
                params={"x": target.position[0], "y": target.position[1]},
            )
        return Action(name="wait", params={"ticks": 1})

    def next_step_toward(
        self, start: Tuple[int, int], target: Tuple[int, int]
    ) -> Tuple[int, int]:
        """获取朝目标移动一步后的坐标。"""
        return self._step_toward(start, target)

    def _update_game_over(self) -> None:
        """检查并更新胜负状态。"""
        alive = [npc for npc in self.npcs.values() if npc.alive]
        if len(alive) <= 1:
            self.game_over = True
            self.winner_id = alive[0].npc_id if alive else None
            if self.winner_id:
                self._log_event(f"胜者：{self.npcs[self.winner_id].name}")
            else:
                self._log_event("无人存活，比赛以同归于尽结束")

    def _spawn_weapon_if_needed(self) -> None:
        """按配置随机刷新武器。"""
        if not self.weapon_pool or self.max_weapons <= 0:
            return
        if len(self.weapons) >= self.max_weapons:
            return
        if self.tick_count % self.spawn_interval_ticks != 0:
            return
        if self.rng.random() > self.spawn_chance:
            return
        position = self._random_empty_position()
        if not position:
            return
        spec = self.rng.choice(self.weapon_pool)
        self._weapon_counter += 1
        instance_id = f"{spec.weapon_id}_{self._weapon_counter:03d}"
        self.weapons[instance_id] = WeaponInstance(
            instance_id=instance_id, spec=spec, position=position
        )
        self._log_event(f"武器刷新：{spec.name} 出现在 {position[0]},{position[1]}")

    def _random_empty_position(self) -> Optional[Tuple[int, int]]:
        """挑选未被占用的随机位置。"""
        occupied = {npc.position for npc in self.npcs.values() if npc.alive}
        occupied.update(weapon.position for weapon in self.weapons.values())
        min_x, max_x = _coordinate_range(self.world_map.width)
        min_y, max_y = _coordinate_range(self.world_map.height)
        for _ in range(50):
            x = self.rng.randint(min_x, max_x)
            y = self.rng.randint(min_y, max_y)
            if not _in_bounds(self.world_map, x, y):
                continue
            if (x, y) in occupied:
                continue
            return (x, y)
        return None

    def _step_toward(self, start: Tuple[int, int], target: Tuple[int, int]) -> Tuple[int, int]:
        """移动一步向目标靠近。"""
        x, y = start
        dx = target[0] - x
        dy = target[1] - y
        step_x, step_y = x, y
        if abs(dx) >= abs(dy) and dx != 0:
            step_x = x + (1 if dx > 0 else -1)
        elif dy != 0:
            step_y = y + (1 if dy > 0 else -1)
        if _in_bounds(self.world_map, step_x, step_y):
            return (step_x, step_y)
        return start

    def _nearest_enemy(self, npc: NPCState) -> Optional[NPCState]:
        """寻找最近的敌对 NPC。"""
        nearest: Optional[NPCState] = None
        best_distance: Optional[int] = None
        for other in self.npcs.values():
            if other.npc_id == npc.npc_id or not other.alive:
                continue
            distance = _manhattan(npc.position, other.position)
            if best_distance is None or distance < best_distance:
                nearest = other
                best_distance = distance
        return nearest

    def _nearest_weapon(self, position: Tuple[int, int]) -> Optional[WeaponInstance]:
        """寻找最近的武器实例。"""
        nearest: Optional[WeaponInstance] = None
        best_distance: Optional[int] = None
        for weapon in self.weapons.values():
            distance = _manhattan(position, weapon.position)
            if best_distance is None or distance < best_distance:
                nearest = weapon
                best_distance = distance
        return nearest

    def _weapon_at_position(self, position: Tuple[int, int]) -> Optional[WeaponInstance]:
        """查找当前位置是否有武器。"""
        for weapon in self.weapons.values():
            if weapon.position == position:
                return weapon
        return None

    def _nearby_weapons(self, position: Tuple[int, int], radius: int) -> List[Dict[str, object]]:
        """获取附近武器列表。"""
        items: List[Dict[str, object]] = []
        for weapon in self.weapons.values():
            if _manhattan(position, weapon.position) <= radius:
                items.append(
                    {
                        "id": weapon.instance_id,
                        "name": weapon.spec.name,
                        "position": {"x": weapon.position[0], "y": weapon.position[1]},
                    }
                )
        return items

    def _observe_nearby(self, npc_id: str, radius: int) -> List[Dict[str, object]]:
        """观察附近 NPC 并返回状态。"""
        observer = self.npcs[npc_id]
        observations: List[Dict[str, object]] = []
        for other in self.npcs.values():
            if other.npc_id == npc_id:
                continue
            if _manhattan(observer.position, other.position) > radius:
                continue
            observations.append(
                {
                    "npc_id": other.npc_id,
                    "name": other.name,
                    "alive": other.alive,
                    "destiny": max(0.0, other.destiny),
                    "position": {"x": other.position[0], "y": other.position[1]},
                    "weapon": other.weapon.name if other.weapon else None,
                }
            )
        return observations

    def _log_event(self, message: str) -> None:
        """记录赛局事件。"""
        cleaned = message.strip()
        if cleaned:
            self.event_log.append(cleaned)


def _coordinate_range(size: int) -> Tuple[int, int]:
    """计算坐标范围。"""
    half = size // 2
    if size % 2 == 0:
        return (-half, half - 1)
    return (-half, half)


def _manhattan(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    """计算曼哈顿距离。"""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _parse_weapon_pool(raw: object, logger: logging.Logger) -> List[WeaponSpec]:
    """解析武器池配置。"""
    if not isinstance(raw, list):
        return [
            WeaponSpec("knife", "Knife", damage=2, range=1, required_level=1),
            WeaponSpec("bow", "Bow", damage=1, range=3, required_level=1),
        ]
    pool: List[WeaponSpec] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        weapon_id = str(entry.get("id") or entry.get("weapon_id") or "").strip()
        name = str(entry.get("name") or weapon_id or "Weapon").strip()
        if not weapon_id:
            weapon_id = name.lower().replace(" ", "_")
        try:
            damage = int(entry.get("damage", 1))
            weapon_range = int(entry.get("range", 1))
            required_level = int(entry.get("required_level", 1))
        except (TypeError, ValueError):
            logger.warning("Invalid weapon config: %s", entry)
            continue
        pool.append(
            WeaponSpec(
                weapon_id=weapon_id,
                name=name,
                damage=damage,
                range=weapon_range,
                required_level=required_level,
            )
        )
    return pool


def _parse_npcs(
    raw: object, world_map: WorldMap, rng: random.Random, logger: logging.Logger
) -> Dict[str, NPCState]:
    """解析 NPC 配置并分配位置。"""
    npcs: Dict[str, NPCState] = {}
    entries = raw if isinstance(raw, list) else []
    if not entries:
        entries = [
            {"id": "NPC-1", "name": "NPC-1"},
            {"id": "NPC-2", "name": "NPC-2"},
            {"id": "NPC-3", "name": "NPC-3"},
        ]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        npc_id = str(entry.get("id") or entry.get("name") or "").strip()
        if not npc_id:
            continue
        name = str(entry.get("name") or npc_id).strip()
        destiny = float(entry.get("destiny", SurvivalWarSession.DEFAULT_DESTINY))
        holder_level = int(entry.get("holder_level", SurvivalWarSession.DEFAULT_HOLDER_LEVEL))
        position = _parse_position(entry.get("position"), world_map, rng)
        npcs[npc_id] = NPCState(
            npc_id=npc_id,
            name=name,
            position=position,
            destiny=destiny,
            holder_level=holder_level,
        )
    if len(npcs) < 3:
        logger.warning("Survival war expects 3 NPCs, got %d", len(npcs))
    return npcs


def _parse_position(
    raw: object, world_map: WorldMap, rng: random.Random
) -> Tuple[int, int]:
    """解析坐标或随机分配位置。"""
    if isinstance(raw, dict):
        try:
            x = int(raw.get("x", 0))
            y = int(raw.get("y", 0))
            if _in_bounds(world_map, x, y):
                return (x, y)
        except (TypeError, ValueError):
            pass
    min_x, max_x = _coordinate_range(world_map.width)
    min_y, max_y = _coordinate_range(world_map.height)
    while True:
        x = rng.randint(min_x, max_x)
        y = rng.randint(min_y, max_y)
        if _in_bounds(world_map, x, y):
            return (x, y)


def _in_bounds(world_map: WorldMap, x: int, y: int) -> bool:
    """判定坐标是否位于地图范围内。"""
    min_x, max_x = _coordinate_range(world_map.width)
    min_y, max_y = _coordinate_range(world_map.height)
    return min_x <= x <= max_x and min_y <= y <= max_y
