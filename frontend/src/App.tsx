import { useCallback, useEffect, useState } from "react";
import { ApiError, createGame, getGame } from "./api";
import type { CreatedGame, GameState, GameView } from "./types";
import EndingView from "./views/EndingView";
import JourneyView from "./views/JourneyView";
import SetupView from "./views/SetupView";

type Phase =
  | { kind: "setup" }
  | { kind: "explore"; gameId: string; state: GameState }
  | { kind: "ending"; view: GameView };

/** 终局侦测轮询间隔（ms）。JourneyView 冻结无状态回调，终局由 App 轮询读局发现。 */
const ENDING_POLL_MS = 2000;

/**
 * 顶层视图机：建局态 → 探索态 → 结局图态。
 * 探索期 App 轮询读局，state.ending 非空 → 切结局图（JourneyView 自身刷新路径不动）；
 * 探索态会话失效（api 404）→ 回建局态。「再入轮回」→ 回建局态（清会话、保留结局进度）。
 */
export default function App() {
  const [phase, setPhase] = useState<Phase>({ kind: "setup" });

  const handleStart = async (name: string) => {
    const created: CreatedGame = await createGame(name);
    setPhase({ kind: "explore", gameId: created.id, state: created.state });
  };

  const handleSessionGone = useCallback(() => setPhase({ kind: "setup" }), []);
  const handleRestart = useCallback(() => setPhase({ kind: "setup" }), []);

  const gameId = phase.kind === "explore" ? phase.gameId : null;

  useEffect(() => {
    if (gameId === null) return;
    // 重入闸：上一轮读局未落定则跳过本 tick，不打并发
    let inFlight = false;
    const timer = setInterval(() => {
      if (inFlight) return;
      inFlight = true;
      getGame(gameId)
        .then((view) => {
          if (view.state.ending !== null) setPhase({ kind: "ending", view });
        })
        .catch((exc: unknown) => {
          // 错误分闸只认 ApiError.status（与 JourneyView 同款）；其余轮询失败不打断探索
          if (exc instanceof ApiError && exc.status === 404) setPhase({ kind: "setup" });
        })
        .finally(() => {
          inFlight = false;
        });
    }, ENDING_POLL_MS);
    return () => clearInterval(timer);
  }, [gameId]);

  if (phase.kind === "setup") {
    return <SetupView onStart={handleStart} />;
  }
  if (phase.kind === "ending") {
    return (
      <EndingView
        endings={phase.view.endings}
        currentEnding={phase.view.state.ending}
        onRestart={handleRestart}
      />
    );
  }
  return (
    <JourneyView
      gameId={phase.gameId}
      initialState={phase.state}
      onSessionGone={handleSessionGone}
    />
  );
}
