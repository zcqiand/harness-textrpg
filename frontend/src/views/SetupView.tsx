import { useState } from "react";

interface SetupViewProps {
  onStart: (name: string) => Promise<void>;
}

/** 建局态：输入名号 → 开始。错误与进行中态就地呈现。 */
export default function SetupView({ onStart }: SetupViewProps) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = name.trim();
  const canStart = trimmed !== "" && !busy;

  const submit = async () => {
    if (!canStart) return;
    setBusy(true);
    setError(null);
    try {
      await onStart(trimmed);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h1>西游记文字冒险</h1>
      <label htmlFor="player-name">名号</label>
      <input
        id="player-name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        disabled={busy}
      />
      <button type="button" onClick={submit} disabled={!canStart}>
        开始
      </button>
      {error !== null && <p role="alert">{error}</p>}
    </section>
  );
}
