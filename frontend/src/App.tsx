import { useCallback, useState } from "react";
import { createGame } from "./api";
import type { CreatedGame, GameState } from "./types";
import JourneyView from "./views/JourneyView";
import SetupView from "./views/SetupView";

type Phase =
  | { kind: "setup" }
  | { kind: "explore"; gameId: string; state: GameState };

/** 顶层视图机：建局态 → 探索态；探索态会话失效（api 404）→ 回建局态。 */
export default function App() {
  const [phase, setPhase] = useState<Phase>({ kind: "setup" });

  const handleStart = async (name: string) => {
    const created: CreatedGame = await createGame(name);
    setPhase({ kind: "explore", gameId: created.id, state: created.state });
  };

  const handleSessionGone = useCallback(() => setPhase({ kind: "setup" }), []);

  if (phase.kind === "setup") {
    return <SetupView onStart={handleStart} />;
  }
  return (
    <JourneyView
      gameId={phase.gameId}
      initialState={phase.state}
      onSessionGone={handleSessionGone}
    />
  );
}
