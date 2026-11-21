import { useCallback, useEffect, useState } from "react";
import { ApiError, fetchNpcMemory, talkToNpc } from "../api";
import type { MemoryEntry } from "../api";
// @entry M03.F04.I01
// @entry M03.F04.I02

interface TalkViewProps {
  gameId: string;
  npcId: string;
  /** 展示名来自 SceneViewV2.npcs（视图层带名）。 */
  npcName: string;
  onBack: () => void;
  onSessionGone: () => void;
}

/** 统一错误分闸：只认 ApiError.status（404=会话失效），不认 message 内容。 */
function isSessionGone(exc: unknown): boolean {
  return exc instanceof ApiError && exc.status === 404;
}

/**
 * NPC 对话视图：记忆历史（GET memory）+ 输入递话（POST talk）。
 * 放行/降级：回复随记忆刷新落进轮次列表，无拦截提示；
 * 被拦（blocked=true）：红线明细逐条可视化，回复不展示、记忆不推进（不二次拉取）。
 * 会话失效（api 404）→ onSessionGone 回建局态。
 */
export default function TalkView({ gameId, npcId, npcName, onBack, onSessionGone }: TalkViewProps) {
  const [entries, setEntries] = useState<MemoryEntry[] | null>(null);
  /** 最近一次被拦输入命中的红线词表；null=当前无拦截提示。 */
  const [guard, setGuard] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");

  const handleFailure = useCallback(
    (exc: unknown) => {
      if (isSessionGone(exc)) {
        onSessionGone();
        return;
      }
      setError(exc instanceof Error ? exc.message : String(exc));
    },
    [onSessionGone],
  );

  const refreshMemory = useCallback((): Promise<void> => {
    return fetchNpcMemory(gameId, npcId)
      .then((view) => {
        setEntries(view.entries);
      })
      .catch((exc: unknown) => {
        handleFailure(exc);
      });
  }, [gameId, npcId, handleFailure]);

  useEffect(() => {
    refreshMemory();
  }, [refreshMemory]);

  const speak = async () => {
    const text = draft.trim();
    if (text === "" || busy) return;
    setBusy(true);
    setError(null);
    setGuard(null);
    try {
      const result = await talkToNpc(gameId, npcId, text);
      if (result.blocked) {
        // 被拦轮不落账（memory_turn=null），回复不可信，只展示红线明细
        setGuard(result.guard_evidence);
      } else {
        setDraft("");
        await refreshMemory();
      }
    } catch (exc) {
      handleFailure(exc);
    } finally {
      setBusy(false);
    }
  };

  const canSpeak = draft.trim() !== "" && !busy;

  return (
    <section aria-label="对话视图">
      <h3>与 {npcName} 对话</h3>
      <button type="button" aria-label="返回旅程" onClick={onBack}>
        返回
      </button>
      {error !== null && <p role="alert">{error}</p>}
      {guard !== null && (
        <div role="alert" aria-label="护栏拦截提示" data-fn="M03.F04.I02">
          <p>此话触犯红线，{npcName} 未听见：</p>
          <ul>
            {guard.map((word, i) => (
              <li key={`${word}-${i}`}>红线：{word}</li>
            ))}
          </ul>
        </div>
      )}
      {entries === null ? (
        <p>回忆装载中……</p>
      ) : entries.length === 0 ? (
        <p>尚无交谈记录</p>
      ) : (
        <ul aria-label="对话记忆">
          {entries.map((entry) => (
            <li key={entry.turn}>
              第{entry.turn}轮：你：「{entry.player_text}」{npcName}：「{entry.npc_text}」
              {entry.event_tags.length > 0 && <span>（记事：{entry.event_tags.join("、")}）</span>}
            </li>
          ))}
        </ul>
      )}
      <input
        aria-label={`对${npcName}说`}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        disabled={busy}
      />
      <button type="button" onClick={speak} disabled={!canSpeak}>
        开口
      </button>
    </section>
  );
}
