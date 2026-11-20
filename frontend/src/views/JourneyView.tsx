import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getGame, submitChoice } from "../api";
import type {
  ChapterView,
  ChoiceView,
  GameView,
  GameState,
  MissingCondition,
  SceneView,
} from "../types";
// @entry M03.F02.I01
// @entry M03.F02.I02

interface JourneyViewProps {
  gameId: string;
  initialState: GameState;
  onSessionGone: () => void;
}

/** 锁条件明细面板里，缺失类型的可读名。 */
const MISSING_TYPE_LABELS: Record<MissingCondition["type"], string> = {
  item: "物品",
  flag: "旗标",
  attr: "属性",
};

/** 布尔量（flag/item 条件）→「有/无」；数值（attr 条件）原样呈现。 */
function formatAmount(value: boolean | number): string {
  return typeof value === "boolean" ? (value ? "有" : "无") : String(value);
}

/** 解锁高亮时长（ms）。 */
const UNLOCK_FLASH_MS = 1500;

/** 统一错误分闸：只认 ApiError.status（404=会话失效），不认 message 内容。 */
function isSessionGone(exc: unknown): boolean {
  return exc instanceof ApiError && exc.status === 404;
}

/**
 * 章回探索态：场景标题 + 抉择列表。
 * 锁抉择 disabled 不可点，但挂一枚「锁」徽标按钮，点击弹条件明细面板
 * （缺失 type/key 与后端 denial 文案）。会话失效（api 404）→ onSessionGone 回建局态。
 * 提交抉择若推开锁（响应 unlocked_locks 非空），对应抉择挂「解锁」徽标高亮 1.5s。
 */
export default function JourneyView({ gameId, initialState, onSessionGone }: JourneyViewProps) {
  const [state, setState] = useState<GameState>(initialState);
  const [chapters, setChapters] = useState<ChapterView[]>([]);
  const [scene, setScene] = useState<SceneView | null>(null);
  const [choices, setChoices] = useState<ChoiceView[] | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** 本轮刚解锁、正处高亮期（1.5s 内）的抉择 id 集。 */
  const [flashIds, setFlashIds] = useState<ReadonlySet<string>>(() => new Set());
  /** per-choice 高亮 timer 表——starter 终审教训：绝不单例 timer，重开必清理。 */
  const flashTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

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

  /** 清光高亮 timer（新抉择提交前与组件卸载各调一次）。 */
  const clearFlashTimers = useCallback(() => {
    for (const timer of flashTimersRef.current.values()) clearTimeout(timer);
    flashTimersRef.current.clear();
  }, []);

  // 卸载清理：不留悬空 timer 去打已卸载组件的 setState。
  useEffect(() => clearFlashTimers, [clearFlashTimers]);

  /** 点亮一批抉择 1.5s；到期逐个熄灭并从 timer 表摘除。 */
  const startFlash = useCallback(
    (choiceIds: string[]) => {
      clearFlashTimers();
      setFlashIds(new Set(choiceIds));
      for (const id of choiceIds) {
        const timer = setTimeout(() => {
          flashTimersRef.current.delete(id);
          setFlashIds((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          });
        }, UNLOCK_FLASH_MS);
        flashTimersRef.current.set(id, timer);
      }
    },
    [clearFlashTimers],
  );

  /** 拉局并落三视图；返回视图供调用方做差集（失败已走 handleFailure，返回 null）。 */
  const refresh = useCallback((): Promise<GameView | null> => {
    return getGame(gameId)
      .then((view) => {
        setState(view.state);
        setScene(view.scene);
        setChapters(view.chapters);
        setChoices(view.choices);
        return view;
      })
      .catch((exc: unknown) => {
        handleFailure(exc);
        return null;
      });
  }, [gameId, handleFailure]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const choose = async (choice: ChoiceView) => {
    if (choice.locked || busy) return;
    const before = choices;
    setBusy(true);
    setError(null);
    // 新抉择提交：上一轮高亮与 timer 一律作废（重开清理）。
    clearFlashTimers();
    setFlashIds(new Set());
    try {
      const result = await submitChoice(gameId, state.current_scene, choice.id);
      const view = await refresh();
      // unlocked_locks 是锁 id，ChoiceView 不带锁引用——
      // 以「本轮 locked → 未锁」差集定位被推开的门对应的抉择。
      if (result.unlocked_locks.length > 0 && before !== null && view !== null) {
        const wasLocked = new Set(before.filter((c) => c.locked).map((c) => c.id));
        const newlyUnlocked = view.choices
          .filter((c) => !c.locked && wasLocked.has(c.id))
          .map((c) => c.id);
        if (newlyUnlocked.length > 0) startFlash(newlyUnlocked);
      }
    } catch (exc) {
      handleFailure(exc);
    } finally {
      setBusy(false);
    }
  };

  const chapterTitle =
    chapters.find((c) => c.id === state.current_chapter)?.title ?? state.current_chapter;

  return (
    <section aria-label="探索视图">
      <h2>{chapterTitle}</h2>
      {scene !== null && <p className="scene-text">{scene.text}</p>}
      {error !== null && <p role="alert">{error}</p>}
      {choices === null ? (
        <p>装载中……</p>
      ) : (
        <ul>
          {choices.map((choice) => (
            <li key={choice.id}>
              <button
                type="button"
                onClick={() => choose(choice)}
                disabled={choice.locked || busy}
              >
                {choice.text}
              </button>
              {flashIds.has(choice.id) && (
                <span role="status" className="unlock-flash">
                  解锁
                </span>
              )}
              {choice.locked && (
                <button
                  type="button"
                  aria-label={`「${choice.text}」未满足条件`}
                  onClick={() => setDetailId(detailId === choice.id ? null : choice.id)}
                >
                  锁
                </button>
              )}
              {choice.locked && detailId === choice.id && (
                <div>
                  {choice.denial !== null && <p>{choice.denial}</p>}
                  {choice.missing.map((m) => (
                    <div key={`${m.type}-${m.key}`}>
                      <p>{`缺失类型：${m.type}`}</p>
                      <p>{`缺失项：${MISSING_TYPE_LABELS[m.type]} ${m.key}（现有 ${formatAmount(m.have)}，需 ${formatAmount(m.need)}）`}</p>
                    </div>
                  ))}
                  <button type="button" onClick={() => setDetailId(null)}>
                    收起
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
