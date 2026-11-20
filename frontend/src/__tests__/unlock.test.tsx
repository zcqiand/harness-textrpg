// 假时钟下 userEvent.click 会挂死（RTL/调度器互踩，jsdom 29 实测），
// 组件行为不依赖输入细节，点击一律走 fireEvent（同步，无 timer 参与）。
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getGame, submitChoice } from "../api";
import JourneyView from "../views/JourneyView";
import type { ChoiceResultView, ChoiceView, GameView } from "../types";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    createGame: vi.fn(),
    getGame: vi.fn(),
    submitChoice: vi.fn(),
    getChapters: vi.fn(),
  };
});

const takeRations: ChoiceView = {
  id: "c_take_rations",
  text: "向村家化些干粮",
  locked: false,
  missing: [],
  denial: null,
};

const talkWoodcutter: ChoiceView = {
  id: "c_talk_woodcutter",
  text: "与门前樵夫攀谈",
  locked: false,
  missing: [],
  denial: null,
};

const leaveLocked: ChoiceView = {
  id: "c_leave",
  text: "辞别村舍，望山而行",
  locked: true,
  missing: [{ type: "item", key: "dry_rations", have: 0, need: 1 }],
  denial: "腹中无粮，如何翻山？先向村家化些干粮再走。",
};

const leaveUnlocked: ChoiceView = { ...leaveLocked, locked: false, missing: [], denial: null };

const gameState = {
  player_name: "悟空",
  flags: [],
  attributes: {},
  backpack: [],
  current_chapter: "ch01",
  current_scene: "s01_village",
  game_over: false,
  ending: null,
};

/** 首屏视图：c_leave 仍挂锁。 */
const initialView: GameView = {
  state: gameState,
  choices: [takeRations, talkWoodcutter, leaveLocked],
  endings: [],
  chapters: [{ id: "ch01", title: "第一回 两界山前", locked: false }],
};

/** 提交化缘后的视图：lock_ch01_rations_gate 已满足，c_leave 解锁。 */
const unlockedView: GameView = {
  state: { ...gameState, backpack: ["dry_rations"] },
  choices: [takeRations, talkWoodcutter, leaveUnlocked],
  endings: [],
  chapters: [{ id: "ch01", title: "第一回 两界山前", locked: false }],
};

const unlockResult: ChoiceResultView = {
  messages: ["干粮入手，行囊稍实。"],
  state: unlockedView.state,
  unlocked_locks: ["lock_ch01_rations_gate"],
  game_over: false,
  ending: null,
};

const emptyResult: ChoiceResultView = { ...unlockResult, unlocked_locks: [] };

/** 假时钟下推进 0ms：冲刷挂起的微任务（mock promise 链），让视图落定。 */
async function flushMicrotasks() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

describe("解锁高亮反馈", () => {
  let onSessionGone: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(getGame).mockReset();
    vi.mocked(submitChoice).mockReset();
    onSessionGone = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("unlocked_locks 非空 → 对应抉择挂「解锁」徽标高亮，1.5s 后消退", async () => {
    vi.mocked(getGame).mockResolvedValueOnce(initialView).mockResolvedValueOnce(unlockedView);
    vi.mocked(submitChoice).mockResolvedValue(unlockResult);
        render(<JourneyView gameId="game-1" initialState={initialView.state} onSessionGone={onSessionGone} />);
    await flushMicrotasks();
    fireEvent.click(screen.getByRole("button", { name: "向村家化些干粮" }));
    await flushMicrotasks();

    const badge = screen.getByText("解锁");
    expect(badge).toHaveClass("unlock-flash");
    expect(onSessionGone).not.toHaveBeenCalled();

    // 1.5s 内高亮仍在
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1499);
    });
    expect(screen.getByText("解锁")).toBeInTheDocument();

    // 推进满 1.5s → 高亮消退
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(screen.queryByText("解锁")).not.toBeInTheDocument();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("unlocked_locks 为空 → 无高亮", async () => {
    vi.mocked(getGame).mockResolvedValue(initialView);
    vi.mocked(submitChoice).mockResolvedValue(emptyResult);
        render(<JourneyView gameId="game-1" initialState={initialView.state} onSessionGone={onSessionGone} />);
    await flushMicrotasks();
    fireEvent.click(screen.getByRole("button", { name: "向村家化些干粮" }));
    await flushMicrotasks();

    expect(screen.queryByText("解锁")).not.toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(screen.queryByText("解锁")).not.toBeInTheDocument();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("新抉择清理上一轮高亮 timer（重开清理，不复活）", async () => {
    vi.mocked(getGame)
      .mockResolvedValueOnce(initialView)
      .mockResolvedValueOnce(unlockedView)
      .mockResolvedValue(unlockedView);
    vi.mocked(submitChoice).mockResolvedValueOnce(unlockResult).mockResolvedValue(emptyResult);
        render(<JourneyView gameId="game-1" initialState={initialView.state} onSessionGone={onSessionGone} />);
    await flushMicrotasks();

    // 第一次提交：解锁高亮出现，1.5s timer 挂起
    fireEvent.click(screen.getByRole("button", { name: "向村家化些干粮" }));
    await flushMicrotasks();
    expect(screen.getByText("解锁")).toBeInTheDocument();
    expect(vi.getTimerCount()).toBe(1);

    // 1.5s 内提交第二个抉择：上一轮 timer 立即清理，徽标不再复活
    fireEvent.click(screen.getByRole("button", { name: "与门前樵夫攀谈" }));
    await flushMicrotasks();
    expect(screen.queryByText("解锁")).not.toBeInTheDocument();
    expect(vi.getTimerCount()).toBe(0);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(screen.queryByText("解锁")).not.toBeInTheDocument();
  });

  it("组件卸载清理 timer", async () => {
    vi.mocked(getGame).mockResolvedValueOnce(initialView).mockResolvedValueOnce(unlockedView);
    vi.mocked(submitChoice).mockResolvedValue(unlockResult);
    const { unmount } = render(
      <JourneyView gameId="game-1" initialState={initialView.state} onSessionGone={onSessionGone} />,
    );
    await flushMicrotasks();
    fireEvent.click(screen.getByRole("button", { name: "向村家化些干粮" }));
    await flushMicrotasks();
    expect(vi.getTimerCount()).toBe(1);

    unmount();
    expect(vi.getTimerCount()).toBe(0);
    // 卸载后推进不炸（无挂起 timer 触发已卸载组件 setState）
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
  });
});
