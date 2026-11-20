/**
 * API client：同源相对 `/api`（禁 env 默认值兜底——suite 硬规则 2026-08-28）。
 * 端点真源 = backend/src/text_rpg/routes.py；形状真源 = src/types.ts。
 */
import type {
  ChapterCatalog,
  ChoiceResultView,
  CreatedGame,
  GameView,
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
export function getGame(gameId: string): Promise<GameView> {
  return request<GameView>(`/games/${encodeURIComponent(gameId)}`);
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
