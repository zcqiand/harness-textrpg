import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getGame, submitChoice } from "../api";
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

const unlockedChoice: ChoiceView = {
  id: "c_take_rations",
  text: "向村家化些干粮",
  locked: false,
  missing: [],
  denial: null,
};

const lockedChoice: ChoiceView = {
  id: "c_leave",
  text: "辞别村舍，望山而行",
  locked: true,
  missing: [{ type: "item", key: "dry_rations", have: 0, need: 1 }],
  denial: "腹中无粮，如何翻山？先向村家化些干粮再走。",
};

const gameView: GameView = {
  state: {
    player_name: "悟空",
    flags: [],
    attributes: {},
    backpack: [],
    current_chapter: "ch01",
    current_scene: "s01_village",
    game_over: false,
    ending: null,
  },
  choices: [unlockedChoice, lockedChoice],
  endings: [],
  chapters: [{ id: "ch01", title: "第一回 两界山前", locked: false }],
};

const choiceResult: ChoiceResultView = {
  messages: ["干粮入手，行囊稍实。"],
  state: {
    player_name: "悟空",
    flags: [],
    attributes: {},
    backpack: ["dry_rations"],
    current_chapter: "ch01",
    current_scene: "s01_village",
    game_over: false,
    ending: null,
  },
  unlocked_locks: [],
  game_over: false,
  ending: null,
};

describe("章回探索态", () => {
  const initialState = gameView.state;
  let onSessionGone: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.mocked(getGame).mockReset();
    vi.mocked(submitChoice).mockReset();
    onSessionGone = vi.fn();
  });

  it("未锁抉择可点击并提交 submitChoice", async () => {
    vi.mocked(getGame).mockResolvedValue(gameView);
    vi.mocked(submitChoice).mockResolvedValue(choiceResult);
    render(
      <JourneyView gameId="game-1" initialState={initialState} onSessionGone={onSessionGone} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "向村家化些干粮" }));
    expect(submitChoice).toHaveBeenCalledWith("game-1", "s01_village", "c_take_rations");
  });

  it("锁抉择灰显（disabled）且挂锁徽标", async () => {
    vi.mocked(getGame).mockResolvedValue(gameView);
    render(
      <JourneyView gameId="game-1" initialState={initialState} onSessionGone={onSessionGone} />,
    );
    expect(await screen.findByRole("button", { name: "辞别村舍，望山而行" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "「辞别村舍，望山而行」未满足条件" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "向村家化些干粮" })).toBeEnabled();
  });

  it("点锁徽标弹条件明细，展示缺失 type/key 与 denial 文案", async () => {
    vi.mocked(getGame).mockResolvedValue(gameView);
    render(
      <JourneyView gameId="game-1" initialState={initialState} onSessionGone={onSessionGone} />,
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "「辞别村舍，望山而行」未满足条件" }),
    );
    expect(
      await screen.findByText("腹中无粮，如何翻山？先向村家化些干粮再走。"),
    ).toBeInTheDocument();
    expect(screen.getByText("缺失类型：item")).toBeInTheDocument();
    expect(screen.getByText("缺失项：物品 dry_rations（现有 0，需 1）")).toBeInTheDocument();
  });

  it("会话失效（api 404）→ 回建局态回调", async () => {
    vi.mocked(getGame).mockRejectedValue(new ApiError(404, "局不存在：game-1"));
    render(
      <JourneyView gameId="game-1" initialState={initialState} onSessionGone={onSessionGone} />,
    );
    await waitFor(() => expect(onSessionGone).toHaveBeenCalledTimes(1));
  });
});
