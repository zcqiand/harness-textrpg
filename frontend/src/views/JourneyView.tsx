import { useCallback, useEffect, useState } from "react";
import { ApiError, getGame, submitChoice } from "../api";
import type { ChapterView, ChoiceView, GameState, MissingCondition } from "../types";

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

/** 统一错误分闸：只认 ApiError.status（404=会话失效），不认 message 内容。 */
function isSessionGone(exc: unknown): boolean {
  return exc instanceof ApiError && exc.status === 404;
}

/**
 * 章回探索态：场景标题 + 抉择列表。
 * 锁抉择 disabled 不可点，但挂一枚「锁」徽标按钮，点击弹条件明细面板
 * （缺失 type/key 与后端 denial 文案）。会话失效（api 404）→ onSessionGone 回建局态。
 */
export default function JourneyView({ gameId, initialState, onSessionGone }: JourneyViewProps) {
  const [state, setState] = useState<GameState>(initialState);
  const [chapters, setChapters] = useState<ChapterView[]>([]);
  const [choices, setChoices] = useState<ChoiceView[] | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  const refresh = useCallback(() => {
    getGame(gameId)
      .then((view) => {
        setState(view.state);
        setChapters(view.chapters);
        setChoices(view.choices);
      })
      .catch(handleFailure);
  }, [gameId, handleFailure]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const choose = async (choice: ChoiceView) => {
    if (choice.locked || busy) return;
    setBusy(true);
    setError(null);
    try {
      await submitChoice(gameId, state.current_scene, choice.id);
      refresh();
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
                      <p>{`缺失项：${MISSING_TYPE_LABELS[m.type]} ${m.key}（现有 ${m.have}，需 ${m.need}）`}</p>
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
