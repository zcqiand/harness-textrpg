import { useState } from "react";
import { createGame } from "./api";
import type { CreatedGame, GameState } from "./types";
import SetupView from "./views/SetupView";

type Phase =
  | { kind: "setup" }
  | { kind: "explore"; gameId: string; state: GameState };

/** 顶层视图机：建局态 → 探索态（探索视图本任务先渲染占位文案）。 */
export default function App() {
  const [phase, setPhase] = useState<Phase>({ kind: "setup" });

  const handleStart = async (name: string) => {
    const created: CreatedGame = await createGame(name);
    setPhase({ kind: "explore", gameId: created.id, state: created.state });
  };

  if (phase.kind === "setup") {
    return <SetupView onStart={handleStart} />;
  }
  return (
    <section>
      <p>探索视图（占位）</p>
    </section>
  );
}
