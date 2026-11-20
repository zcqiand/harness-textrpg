import { useEffect, useState } from "react";
import type { Ending, EndingView as EndingRow, MissingCondition } from "../types";

interface EndingViewProps {
  /** 全部结局行（后端 endings_view，satisfied 为当前局内即时求值）。 */
  endings: EndingRow[];
  /** 本局触发的结局（state.ending；null = 未触发，仅展示图）。 */
  currentEnding: Ending | null;
  /** 「再入轮回」：回建局态（清当前会话 id，保留结局进度）。 */
  onRestart: () => void;
}

/** 跨局结局进度 localStorage 键（值 = 已见结局 id 的 JSON 数组）。 */
const ENDINGS_KEY = "htextrpg-endings";

/** 缺失类型的可读名（与 JourneyView 明细面板同款分叉）。 */
const MISSING_TYPE_LABELS: Record<MissingCondition["type"], string> = {
  item: "物品",
  flag: "旗标",
  attr: "属性",
};

/**
 * 读已见结局 id 集。返回 null = 读失败（存储不可用）——
 * 调用方按「无跨局记忆」处理：全灰且不回写。
 */
function readStoredEndingIds(): string[] | null {
  try {
    const raw = window.localStorage.getItem(ENDINGS_KEY);
    if (raw === null) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((x): x is string => typeof x === "string");
  } catch {
    return null;
  }
}

/** 回写合并结果。写失败不致命：本局点亮不受影响，仅跨局记忆缺失。 */
function writeStoredEndingIds(ids: string[]): void {
  try {
    window.localStorage.setItem(ENDINGS_KEY, JSON.stringify(ids));
  } catch {
    // 静默：隐私模式/配额满等场景下不拦结局图呈现
  }
}

/**
 * 结局图态：每枚结局一张卡片。点亮 = 当前局 satisfied 或 id 已入跨局进度集；
 * 未达卡片挂缺失条件链（type/key 与 have/need）。挂载时合并本局结局并回写
 * localStorage（读失败 → 全灰、不回写，页面照常呈现）。
 */
export default function EndingView({ endings, currentEnding, onRestart }: EndingViewProps) {
  const [litIds, setLitIds] = useState<ReadonlySet<string>>(() => new Set());

  useEffect(() => {
    const stored = readStoredEndingIds();
    if (stored === null) return;
    const merged = new Set(stored);
    if (currentEnding !== null) merged.add(currentEnding.id);
    setLitIds(merged);
    writeStoredEndingIds([...merged]);
  }, [currentEnding]);

  return (
    <section aria-label="结局图">
      <h2>轮回结局图</h2>
      <ul>
        {endings.map((ending) => {
          const lit = ending.satisfied || litIds.has(ending.id);
          return (
            <li key={ending.id} className={lit ? "ending-card ending-lit" : "ending-card"}>
              <h3>{ending.title}</h3>
              {lit ? (
                <p role="status">已见证</p>
              ) : (
                <div>
                  <p>未达</p>
                  {ending.missing.map((m) => (
                    <div key={`${m.type}-${m.key}`}>
                      <p>{`缺失类型：${m.type}`}</p>
                      <p>{`缺失项：${MISSING_TYPE_LABELS[m.type]} ${m.key}（现有 ${m.have}，需 ${m.need}）`}</p>
                    </div>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <button type="button" onClick={onRestart}>
        再入轮回
      </button>
    </section>
  );
}
