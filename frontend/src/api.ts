/**
 * API client：同源相对 `/api`（禁 env 默认值兜底——suite 硬规则 2026-08-28）。
 * 端点真源 = backend/src/text_rpg/routes.py；形状真源 = src/types.ts。
 */
import type {
  ChapterCatalog,
  ChoiceResultView,
  CreatedGame,
  GameView,
  SceneView,
} from "./types";

const API_BASE = "/api";

/** 非 2xx 响应：带 HTTP 状态码与后端 detail 文案。 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, detail: string) {
    super(`HTTP ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, init);
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = (await resp.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // 非 JSON 错误体 → 保留 statusText
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

/** 静态章目录：id/title/序，无局上下文。 */
export function getChapters(): Promise<ChapterCatalog> {
  return request<ChapterCatalog>("/chapters");
}

/** 建局（201）。空/空白名 → 400；非字符串名 → 422（见 types.ts 注）。 */
export function createGame(playerName: string): Promise<CreatedGame> {
  return request<CreatedGame>("/games", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_name: playerName }),
  });
}

/** 读局：state + choices/endings/chapters 三视图。未知 id → 404。 */
export function getGame(gameId: string): Promise<GameViewV2> {
  return request<GameViewV2>(`/games/${encodeURIComponent(gameId)}`);
}

/** 提交抉择。未知 scene/choice 或终局后提交 → 400。 */
export function submitChoice(
  gameId: string,
  sceneId: string,
  choiceId: string,
): Promise<ChoiceResultView> {
  return request<ChoiceResultView>(
    `/games/${encodeURIComponent(gameId)}/choice`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scene_id: sceneId, choice_id: choiceId }),
    },
  );
}

/* ---------- v2：NPC 对话面（routes.py _scene_view / npc_talk / npc_memory 同形） ---------- */

/**
 * v2 场景视图：在 v1 {id, text} 上挂 NPC 入口（routes.py _scene_view 恒下发
 * npcs 数组，元素 {id, name}，视图层带名——数据面 npc_ids 不动）。可选标注：
 * v1 测试夹具无此键，前端以「缺省=无 NPC」容错。
 */
export interface NpcRef {
  id: string;
  name: string;
}

export interface SceneViewV2 extends SceneView {
  npcs?: NpcRef[];
}

/** GET /api/games/{id}（v2）：scene 携 npcs（{id,name}，视图层带名）。 */
export interface GameViewV2 extends GameView {
  scene: SceneViewV2;
}

/** 记忆条目（memory.py record 落账形状）。 */
export interface MemoryEntry {
  turn: number;
  player_text: string;
  npc_text: string;
  event_tags: string[];
}

/** GET /api/games/{id}/npcs/{npc_id}/memory 响应。 */
export interface NpcMemoryView {
  entries: MemoryEntry[];
}

/**
 * POST /api/games/{id}/npcs/{npc_id}/talk 响应：恒四键（放行时
 * guard_evidence=[]；被拦轮 memory_turn=null 不计轮次）。
 */
export interface TalkResultView {
  reply: string;
  blocked: boolean;
  guard_evidence: string[];
  memory_turn: number | null;
}

/** 对某 NPC 说一句话。空/空白输入后端 400；NPC 不在当前场景 400；未知 NPC 404。 */
export function talkToNpc(gameId: string, npcId: string, text: string): Promise<TalkResultView> {
  return request<TalkResultView>(
    `/games/${encodeURIComponent(gameId)}/npcs/${encodeURIComponent(npcId)}/talk`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    },
  );
}

/** 读某 NPC 的对话记忆全量清单（被拦轮不落账，故轮次有跳档属正常）。 */
export function fetchNpcMemory(gameId: string, npcId: string): Promise<NpcMemoryView> {
  return request<NpcMemoryView>(
    `/games/${encodeURIComponent(gameId)}/npcs/${encodeURIComponent(npcId)}/memory`,
  );
}
