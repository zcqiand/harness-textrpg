/**
 * API 响应类型全集。形状真源 = backend/src/text_rpg/routes.py + tests/test_api.py
 * （spec §5.3）。字段逐一对齐 Task 6 实际响应体，勿凭猜测增删。
 */

/** 终局回执（state.ending 与 choice 响应顶层 ending 同形）。 */
export interface Ending {
  id: string;
  title: string;
}

/**
 * 玩家状态。flags 是 sorted list（后端 set → sorted），
 * 章完成旗形状 = `chapter_<章id>_complete`（如 `chapter_ch01_complete`）。
 */
export interface GameState {
  player_name: string;
  flags: string[];
  attributes: Record<string, number>;
  backpack: string[];
  current_chapter: string;
  current_scene: string;
  game_over: boolean;
  ending: Ending | null;
}

/** 未满足条件摘要：type ∈ flag / attr（含 op+value）/ item。 */
export interface MissingCondition {
  type: "flag" | "attr" | "item";
  key: string;
  have: boolean | number;
  need: boolean | number;
}

/** 抉择视图（GET /api/games/{id} 的 choices 行，锁评估已由后端做完）。 */
export interface ChoiceView {
  id: string;
  text: string;
  locked: boolean;
  missing: MissingCondition[];
  denial: string | null;
}

/** 结局视图（endings 行：结局条件链摘要）。 */
export interface EndingView {
  id: string;
  title: string;
  satisfied: boolean;
  missing: MissingCondition[];
}

/** 章视图（chapters 行：entry_lock 求值后的锁定态）。 */
export interface ChapterView {
  id: string;
  title: string;
  locked: boolean;
}

/** 静态章目录行（GET /api/chapters，无局上下文，不携带 locked）。 */
export interface ChapterRow {
  id: string;
  title: string;
  order: number;
}

export interface ChapterCatalog {
  chapters: ChapterRow[];
}

/**
 * POST /api/games 响应（201）。
 *
 * player_name 错误形状分叉（Task 6 deferred minor，T10 记档）：
 * 空 / 纯空白 / 缺失 → 400（routes.py 手查，detail=「player_name 必填且不能为空白」）；
 * 非 JSON string（如 number）→ pydantic 校验 422。前端两态都要认。
 */
export interface CreatedGame {
  id: string;
  state: GameState;
}

/** GET /api/games/{id}：state + 三视图四件。 */
export interface GameView {
  state: GameState;
  choices: ChoiceView[];
  endings: EndingView[];
  chapters: ChapterView[];
}

/** POST /api/games/{id}/choice 响应（终局后提交 → 400）。 */
export interface ChoiceResultView {
  messages: string[];
  state: GameState;
  unlocked_locks: string[];
  game_over: boolean;
  ending: Ending | null;
}
