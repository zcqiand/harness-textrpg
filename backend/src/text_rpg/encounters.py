"""Encounter template loader, audit & seeded generator (spec 5.6).

Audit checks (same shape as opponents.audit_opponents):
1. quantity gate (total templates < 2) -> error
2. dangling placeholder in scene_template (not declared in params) -> reject
3. blank denial in any lock slot -> reject
4. empty slots: blank scene_template / empty lock_slots / empty effect_slots -> reject
5. difficulty broken: missing key / non-int (bool rejected) / negative value -> reject
6. blank word surface: name blank -> reject

Seeded generator `generate_encounter(template, params, seed)`:
random.Random(seed) 实例化（禁全局 random）→ params 填充场景模板占位符 → 锁槽逐一自检
→ 种子化实例化锁 → 无效过滤五查 → 候选奇遇（形状对齐 v1 章包）。
锚纪律裁定（spec §5.6）：生成锁不进 lock_anchors 静态锚表——生成锁的锚由生成器派生标注，
锚纪律由模板级双向断言承担（tests/test_encounters.py::test_template_level_bidirectional_*）。

准入通道 admit（M02.F07.I03）：生成锁并入临时注册表跑 v1 audit 三查（悬空/空 denial/锚）
→ 通过者作临时场景并入当前章（内存态，不落盘，不迁移玩家）；生成锁自带锚注记进
自审锚表（不进静态锚表）。同候选重复准入幂等（场景/锁已登记不重挂）。异源撞车
（T16 审查阻断）：生成 scene_id / 锁 id 已被其他来源登记且内容分歧 → 拒绝报因带 id
（禁静默留旧版还回 200，400 报因面收敛在路由层）。
"""
# @impl M04.F03.I02
# @impl M02.F07.I01
# @impl M02.F07.I03

from __future__ import annotations

import random
import re
from dataclasses import dataclass, replace
from pathlib import Path

from text_rpg.chapters import Choice, LockDef, Scene, World, _read_json
from text_rpg.locks import AuditReport
from text_rpg.locks import audit as audit_locks

__all__ = [
    "EncounterCandidate",
    "EncounterRejectedError",
    "EncounterTemplate",
    "ADMIT_SEED_SCAN_LIMIT",
    "admit",
    "audit_encounter_templates",
    "encounter_template_from_dict",
    "generate_encounter",
    "load_encounter_templates",
]


@dataclass
class EncounterTemplate:
    id: str
    name: str
    params: list[str]
    scene_template: str
    lock_slots: list[dict]
    effect_slots: list[dict]
    difficulty: dict[str, int]


def _params_list(params) -> list[str]:
    """params 非 list 早炸（str 会按字符静默拆散，报错须近根因）。"""
    if not isinstance(params, list):
        raise ValueError(f"params 必须是 list，得到 {type(params).__name__}")
    return [str(p) for p in params]


def _lock_slot(slot: dict) -> dict:
    """锁槽深一层复制；缺 requires 带模板槽位上下文（裸 KeyError 丢上下文）。"""
    if not isinstance(slot.get("requires"), list):
        raise KeyError(f"锁槽缺 requires 列表（slot={slot.get('id', '?')}）")
    return dict(slot, requires=[dict(r) for r in slot["requires"]])


def _effect_slot(eff: dict) -> dict:
    """效果槽含内层 delta dict 复制一层（注释宣称的隔离须真隔离）。"""
    copied = dict(eff)
    for key, value in eff.items():
        if isinstance(value, dict):
            copied[key] = dict(value)
    return copied


def encounter_template_from_dict(d: dict) -> EncounterTemplate:
    if not isinstance(d, dict):
        raise ValueError("奇遇模板契约必须是 dict")
    missing = [
        k
        for k in (
            "id",
            "name",
            "params",
            "scene_template",
            "lock_slots",
            "effect_slots",
            "difficulty",
        )
        if k not in d
    ]
    if missing:
        raise KeyError(f"奇遇模板契约缺必填字段：{missing}")
    return EncounterTemplate(
        id=str(d["id"]),
        name=str(d["name"]),
        params=_params_list(d["params"]),
        scene_template=str(d["scene_template"]),
        # 槽位列表逐行 dict 复制一层（v2 深拷贝教训对齐）：嵌套 dict 不复制会与
        # 调用方源 dict 共享引用，运行期改写回灌契约源。
        lock_slots=[_lock_slot(slot) for slot in d["lock_slots"]],
        effect_slots=[_effect_slot(eff) for eff in d["effect_slots"]],
        difficulty={str(k): int(v) for k, v in dict(d["difficulty"]).items()},
    )


def load_encounter_templates(data_dir: Path) -> list[EncounterTemplate]:
    templates_path = Path(data_dir) / "encounter-templates"
    if not templates_path.is_dir():
        raise FileNotFoundError(f"奇遇模板目录缺失：{templates_path}（fail-fast，禁静默返空集）")
    packs = sorted(templates_path.glob("*.json"), key=lambda p: p.name)
    if not packs:
        raise ValueError(f"奇遇模板目录空（零模板文件）：{templates_path}（奇遇功能面不得静默死）")
    return [encounter_template_from_dict(_read_json(p)) for p in packs]


def audit_encounter_templates(templates: list) -> AuditReport:
    errors = []
    warnings = []
    # 量口径入闸（M02.F07.I01 契约：奇遇模板总数 ≥2，spec §6 留书稿练习新增空间）：
    # 总数 <2 红。
    if len(templates) < 2:
        errors.append(f"奇遇模板总数不足：{len(templates)} < 2（M02.F07.I01：至少 2 个模板）")
    for t in templates:
        # 空白词面：name 空串/纯空白红。
        if not t.name.strip():
            errors.append(f"奇遇模板「{t.id}」name 为空串/纯空白词面（M02.F07.I01）")
        # 空槽位：场景文本模板空白红。
        if not t.scene_template.strip():
            errors.append(
                f"奇遇模板「{t.id}」scene_template 为空串/纯空白（场景骨架面不得为空）"
                f"（M02.F07.I01）"
            )
        # 悬空引用：场景文本模板 {param} 占位未在 params 声明 → 红。
        declared = set(t.params)
        used = set(re.findall(r"\{(\w+)\}", t.scene_template))
        dangling = sorted(used - declared)
        if dangling:
            errors.append(
                f"奇遇模板「{t.id}」scene_template 悬空占位 {dangling}（未在 params 声明）"
                f"（M02.F07.I01）"
            )
        # 空槽位：锁条件槽空红。
        if not isinstance(t.lock_slots, list) or not t.lock_slots:
            errors.append(f"奇遇模板「{t.id}」lock_slots 为空（锁条件槽不得为空）（M02.F07.I01）")
        else:
            for i, slot in enumerate(t.lock_slots):
                slot_id = slot.get("id") if isinstance(slot, dict) else None
                if not isinstance(slot_id, str) or not slot_id.strip():
                    errors.append(
                        f"奇遇模板「{t.id}」lock_slots[{i}] id 为空串/纯空白词面（M02.F07.I01）"
                    )
                requires = slot.get("requires") if isinstance(slot, dict) else None
                if not isinstance(requires, list) or not requires:
                    errors.append(
                        f"奇遇模板「{t.id}」lock_slots[{i}] requires 为空"
                        f"（锁条件面不得为空）（M02.F07.I01）"
                    )
                denial = slot.get("denial") if isinstance(slot, dict) else None
                if not isinstance(denial, str) or not denial.strip():
                    errors.append(
                        f"奇遇模板「{t.id}」lock_slots[{i}] denial 为空串/纯空白（空 denial 红）"
                        f"（M02.F07.I01）"
                    )
        # 空槽位：效果槽空红；行形状校验（v1 效果四类）。
        if not isinstance(t.effect_slots, list) or not t.effect_slots:
            errors.append(f"奇遇模板「{t.id}」effect_slots 为空（效果槽不得为空）（M02.F07.I01）")
        else:
            allowed = {"attr", "item_add", "item_remove", "flag"}
            for i, eff in enumerate(t.effect_slots):
                keys = set(eff) if isinstance(eff, dict) else set()
                if len(keys) != 1 or not keys <= allowed:
                    errors.append(
                        f"奇遇模板「{t.id}」effect_slots[{i}] 形状不符（须为 v1 效果四类单键）"
                        f"（M02.F07.I01）"
                    )
        # 难度规约：键缺失红；值非 int（bool 拒）/负数红。
        difficulty = t.difficulty
        for key in ("attr_min", "locks_max"):
            if key not in difficulty:
                errors.append(
                    f"奇遇模板「{t.id}」difficulty 缺键 {key}（难度规约键必须齐）（M02.F07.I01）"
                )
        for key, value in difficulty.items():
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(
                    f"奇遇模板「{t.id}」difficulty.{key} 须为非负 int，实得非 int 值（M02.F07.I01）"
                )
            elif value < 0:
                errors.append(
                    f"奇遇模板「{t.id}」difficulty.{key} 为负数（难度规约禁负值）（M02.F07.I01）"
                )
    return AuditReport(errors=errors, warnings=warnings)


# --------------------------------------------- 种子化生成器与无效过滤（M02.F07.I02，spec §5.6）

# 生成带上限：锁数由种子在 [1, BAND] 内决定；生成带故意宽于真模板 locks_max（2/3），
# 超出难度规约的部分由过滤环节拒收——过滤器干真活，不是空转摆设。
_ENCOUNTER_LOCK_BAND_MAX = 4


class EncounterRejectedError(ValueError):
    """生成即自检拒收：message 即报因。拒收原因：引用悬空 / 锁槽 id 为空（缺锚）/
    空 denial / 锁条件槽为空（入闸）/ 超锁上限 / 难度缺键（禁软兜底）/ 难度越界 /
    准入撞车（scene_id / 锁 id 被其他来源登记且内容分歧，T16 审查阻断——准入通道
    据此回 400 报因）。"""


@dataclass
class EncounterCandidate:
    """候选奇遇（形状对齐 v1 章包）：scene/locks/effects 三面 + 模板出处。"""

    template_id: str
    name: str
    scene: dict
    locks: list[dict]
    effects: list[dict]


def _derive_anchor(template_id: str, lock_id: str) -> dict:
    """生成锁锚派生：spec §5.6 裁定——锚纪律由模板级双向断言承担，锁体携带锚注记，
    不进 lock_anchors 静态锚表（静态锁照旧全锚不变）。"""
    label = f"{template_id}:{lock_id}"
    return {
        "pass": f"test_encounter_lock_pass[{label}]",
        "deny": f"test_encounter_lock_deny[{label}]",
    }


def _fill_scene(scene_template: str, params: dict) -> str:
    """params 填充 scene_template {占位}；未声明的占位原样保留（交给悬空检查拒收）。"""

    def repl(match: re.Match) -> str:
        key = match.group(1)
        if key in params:
            return str(params[key])
        return match.group(0)

    return re.sub(r"\{(\w+)\}", repl, scene_template)


def generate_encounter(template: EncounterTemplate, params: dict, seed) -> EncounterCandidate:
    """种子化生成候选奇遇：生成即自检，无效即拒收并报因（EncounterRejectedError）。

    流程：random.Random(seed) 实例化 → params 填充占位符 → 入闸（锁条件槽为空即拒收）
    → 锁槽自检（锁槽 id 为空/空 denial）→ 种子化实例化锁（生成带内种子定数）
    → 超锁上限/难度缺键/难度越界过滤 → 候选奇遇。
    同种子+同模板+同参数 → 结果全等（重放地基，T16 准入同局重放全等依赖此）。
    """
    if not isinstance(params, dict):
        raise ValueError(f"params 必须是 dict，得到 {type(params).__name__}")

    # 入闸（锁条件槽为空）：lock_slots 空 → 种子化实例化的取模步长为零会直接
    # ZeroDivisionError——入闸即拒收并报因，与 audit「锁条件槽不得为空」同口径。
    if not template.lock_slots:
        raise EncounterRejectedError(
            f"奇遇「{template.id}」锁条件槽为空：lock_slots 为空（锁条件槽不得为空，M02.F07.I02）"
        )

    # 一查（引用悬空）：填充后残留 {占位} = 生成物引用了未提供的参数 → 拒收并报因。
    # （对齐 v1 audit 悬空占位机制；世界面悬空由 T16 锁注册表自审兜底。）
    filled = _fill_scene(template.scene_template, params)
    leftover = sorted(set(re.findall(r"\{(\w+)\}", filled)))
    if leftover:
        raise EncounterRejectedError(
            f"奇遇「{template.id}」引用悬空：占位 {leftover} 未被 params 填充"
            f"（悬空占位即拒收，M02.F07.I02）"
        )

    # 二查（锁槽 id 为空 / 空 denial）：锁槽逐一自检——锁槽 id 空白即拒收。
    # （T15 审查裁定：_derive_anchor 恒产非空串，「锚派生为空」析取支装饰性恒假，
    # 删除；真触发=锁槽 id 为空——生成锁 id 与断言锚均由槽位 id 派生，id 空则锁不成立。）
    for slot in template.lock_slots:
        lock_id = str(slot.get("id", "")).strip()
        if not lock_id:
            raise EncounterRejectedError(
                f"奇遇「{template.id}」缺锚：锁槽 id 为空"
                f"（生成锁 id 与断言锚均由槽位 id 派生，id 空则锁不成立，M02.F07.I02）"
            )
        denial = slot.get("denial")
        if not isinstance(denial, str) or not denial.strip():
            raise EncounterRejectedError(
                f"奇遇「{template.id}」空 denial：锁「{lock_id}」denial 为空白"
                f"（玩家必须读得懂缺什么，M02.F07.I02）"
            )

    # 种子化实例化：锁数由种子在生成带 [1, BAND] 内决定；槽位循环取用，
    # 同槽复用加 __r<N> 后缀（锁 id 不撞车）。
    rng = random.Random(seed)
    count = rng.randint(1, _ENCOUNTER_LOCK_BAND_MAX)
    locks: list[dict] = []
    slot_uses: dict[str, int] = {}
    for k in range(count):
        slot = template.lock_slots[k % len(template.lock_slots)]
        base = str(slot.get("id", "")).strip()
        used = slot_uses.get(base, 0)
        slot_uses[base] = used + 1
        lock_id = base if used == 0 else f"{base}__r{used}"
        locks.append(
            {
                "id": lock_id,
                "requires": [dict(cond) for cond in slot["requires"]],
                "denial": slot["denial"],
                "effects": [],
                "chapter_id": "",
                "assertion_anchor": _derive_anchor(template.id, lock_id),
            }
        )

    # 三查（超锁上限）：生成锁数 > difficulty.locks_max → 拒收并报因；
    # locks_max 缺键即拒收（T15 审查裁定：缺难度规约就静默放行是软兜底，禁）。
    locks_max = template.difficulty.get("locks_max")
    if locks_max is None:
        raise EncounterRejectedError(
            f"奇遇「{template.id}」难度缺键：difficulty.locks_max 缺失"
            f"（难度规约键必须齐，禁软兜底，M02.F07.I02）"
        )
    if count > locks_max:
        raise EncounterRejectedError(
            f"奇遇「{template.id}」超锁上限：生成锁数 {count} > locks_max={locks_max}"
            f"（难度越界即拒收，M02.F07.I02）"
        )

    # 四查（难度越界-attr）：任一生成锁所需 attr 条件所需值 < attr_min → 拒收并报因；
    # attr_min 缺键即拒收（T15 审查裁定：缺难度规约就静默跳过是软兜底，禁）。
    attr_min = template.difficulty.get("attr_min")
    if attr_min is None:
        raise EncounterRejectedError(
            f"奇遇「{template.id}」难度缺键：difficulty.attr_min 缺失"
            f"（难度规约键必须齐，禁软兜底，M02.F07.I02）"
        )
    for lock in locks:
        for cond in lock["requires"]:
            if not isinstance(cond, dict) or "attr" not in cond:
                continue
            need = cond.get("value")
            if isinstance(need, int) and not isinstance(need, bool) and need < attr_min:
                raise EncounterRejectedError(
                    f"奇遇「{template.id}」难度越界：锁「{lock['id']}」所需"
                    f" attr {cond.get('attr')}={need} < attr_min={attr_min}"
                    f"（M02.F07.I02）"
                )

    # 效果面（v1 四类深一层复制，不回灌模板源）与场景面组装。
    effects = [_effect_slot(eff) for eff in template.effect_slots]
    # T15 审查裁定：admit_choice["effects"] 与 candidate.effects 此前共享同一 list
    # （别名），运行期改写其一即回灌另一容器——list(effects) 断开容器级别名
    # （元素 dict 仍为各自独立副本，_effect_slot 已深一层复制）。
    admit_choice = {
        "id": f"c_admit_{template.id}",
        "text": f"应下这段奇遇：{template.name}",
        "lock": locks[0]["id"],
        "effects": list(effects),
    }
    scene = {
        "id": f"{template.id}_enc",
        "text": filled,
        "npc_ids": [],
        "choices": [admit_choice],
    }
    return EncounterCandidate(
        template_id=template.id, name=template.name, scene=scene, locks=locks, effects=effects
    )


# --------------------------------------------- 奇遇准入通道（M02.F07.I03，spec §5.6）

# 准入种子扫描上限：服务端从局状态派生种子基，基起逐个偏移扫描首个过五类无效过滤的
# 种子。扫描序确定性（同局状态 → 同基 → 同选中种子 → 重放全等）；上限兜住坏模板
# （全种子拒收时不无限循环，超限 400 报因）。
ADMIT_SEED_SCAN_LIMIT = 64


def _scene_from_candidate(candidate: EncounterCandidate) -> Scene:
    """候选奇遇 scene dict → v1 Scene dataclass（choices 内层 effects 逐条复制）。"""
    return Scene(
        id=str(candidate.scene["id"]),
        text=str(candidate.scene["text"]),
        npc_ids=[str(x) for x in candidate.scene.get("npc_ids", [])],
        choices=[
            Choice(
                id=str(c["id"]),
                text=str(c["text"]),
                lock=c.get("lock"),
                goto=c.get("goto"),
                effects=[dict(eff) for eff in c.get("effects", [])],
            )
            for c in candidate.scene.get("choices", [])
        ],
    )


def admit(candidate: EncounterCandidate, engine, state, static_anchors: dict) -> dict:
    """奇遇准入通道（spec §5.6）：生成锁并入临时注册表跑 v1 audit 三查（悬空/空
    denial/锚），通过后作临时场景并入当前章——内存态并轨：章场景清单追加 + 引擎
    场景索引/锁注册表登记（engine.py 本批不动，`_scenes` 私有索引在此同步）。
    生成锁自带锚注记进自审锚表，不进静态锚表。同候选重复准入幂等
    (场景/锁已登记不重挂，重放全等依赖此）。异源撞车（T16 审查阻断）：
    生成 scene_id / 锁 id 已被其他来源登记且内容与本候选分歧 → EncounterRejectedError
    报因带 id（幂等放行只认「内容全等的本候选重入」，禁静默留旧版还回 200）。
    自审不过 → EncounterRejectedError 报因（400 报因面收敛在路由层）。"""
    chapter = next((c for c in engine.world.chapters if c.id == state.current_chapter), None)
    if chapter is None:
        raise EncounterRejectedError(
            f"奇遇准入失败：当前章「{state.current_chapter}」不存在（准入通道拒绝）"
        )
    scene = _scene_from_candidate(candidate)
    scene_id = scene.id
    # 生成锁 → v1 LockDef（临时注册表成员；requires/effects 逐条复制不回灌候选源）。
    gen_locks: dict[str, LockDef] = {}
    for lk in candidate.locks:
        effects = lk.get("effects", [])
        gen_locks[lk["id"]] = LockDef(
            id=lk["id"],
            requires=[dict(cond) for cond in lk["requires"]],
            denial=lk["denial"],
            effects=[dict(eff) for eff in effects] if isinstance(effects, list) else [],
            chapter_id=chapter.id,
        )
    # 撞车闸（T16 审查阻断，先于自审）：同 id 已登记且内容分歧 = 异源撞车即拒收。
    # 幂等放行只认内容全等的本候选重入（同种子+同模板+同参数 → 生成物全等，
    # generate_encounter 重放地基担保）；内容分歧（如局状态漂移重填参数面、静态
    # 场景撞名）在此报因带 id——旧形状自审面 update 撞 id 用生成版、落地面
    # setdefault 撞 id 留旧版，同 id 两路不同物且玩家拿 200 读不到本候选场景。
    registered_scene = engine._scenes.get(scene_id)
    if registered_scene is not None and registered_scene != scene:
        raise EncounterRejectedError(
            f"奇遇准入撞车：场景 id「{scene_id}」已被其他来源登记，"
            f"本候选生成物与已登记版内容分歧（异源撞车即拒绝，禁静默留旧版）"
        )
    for lock_id, lock_def in gen_locks.items():
        registered_lock = engine.registry.get(lock_id)
        if registered_lock is not None and registered_lock != lock_def:
            raise EncounterRejectedError(
                f"奇遇准入撞车：锁 id「{lock_id}」已被其他来源登记，"
                f"本候选生成锁与已登记版内容分歧（异源撞车即拒绝，禁静默留旧版）"
            )
    # 临时注册表 = 静态 ∪ 生成锁；自审锚表 = 静态锚 ∪ 生成锁自带锚注记。
    merged_registry = dict(engine.registry)
    merged_registry.update(gen_locks)
    merged_anchors = dict(static_anchors)
    for lk in candidate.locks:
        merged_anchors[lk["id"]] = dict(lk["assertion_anchor"])
    # 临时世界：当前章替换为「原场景 + 临时场景」浅拷贝（自审不过不污染真世界）。
    temp_world = World(
        chapters=[
            replace(c, scenes=[*c.scenes, scene]) if c.id == chapter.id else c
            for c in engine.world.chapters
        ],
        start_attributes={},
        start_backpack=[],
    )
    report = audit_locks(temp_world, merged_registry, merged_anchors)
    if report.errors:
        raise EncounterRejectedError("奇遇准入自审未通过：" + "；".join(report.errors))
    # 自审通过 → 内存态并轨：场景入当前章场景清单 + 引擎索引/注册表登记（幂等）。
    # engine._scenes 为引擎私有索引（engine.py 本批不动，批次边界），在此同步登记。
    if all(s.id != scene_id for s in chapter.scenes):
        chapter.scenes.append(scene)
    for lock_id, lock_def in gen_locks.items():
        engine.registry.setdefault(lock_id, lock_def)
    engine._scenes.setdefault(scene_id, scene)
    return {"scene_id": scene_id, "lock_ids": [lk["id"] for lk in candidate.locks]}
