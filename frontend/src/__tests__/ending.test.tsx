// 假时钟下 userEvent.click 会挂死（jsdom 29 × user-event 14.5.2 × React 19，T12 实测），
// 全部交互走 fireEvent（同步，无 timer 参与）。
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createGame, getGame } from "../api";
import App from "../App";
import EndingView from "../views/EndingView";
import type { CreatedGame, EndingView as EndingRow, GameView, GameState } from "../types";

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

/** 全 4 结局行（真实世界 = ch01→ch03 拼接；satisfied/missing 按局内状态不同而变）。 */
function endingRows(satisfiedId: string | null): EndingRow[] {
  const row = (
    id: string,
    title: string,
    missing: EndingRow["missing"],
  ): EndingRow => ({
    id,
    title,
    satisfied: id === satisfiedId,
    missing: id === satisfiedId ? [] : missing,
  });
  return [
    row("turned_back", "半途折返", [
      { type: "flag", key: "went_long_way", have: false, need: true },
    ]),
    row("banished_early", "被逐早终", [
      { type: "flag", key: "struck_without_evidence", have: false, need: true },
    ]),
    row("true_form", "现形归真", [
      { type: "flag", key: "bone_spirit_exposed", have: false, need: true },
      { type: "flag", key: "true_fan", have: false, need: true },
    ]),
    row("west_won", "借扇西行", [
      { type: "item", key: "banana_leaf_fan", have: 0, need: 1 },
    ]),
  ];
}

const normalState: GameState = {
  player_name: "悟空",
  flags: [],
  attributes: { insight: 1 },
  backpack: [],
  current_chapter: "ch01",
  current_scene: "s01_village",
  game_over: false,
  ending: null,
};

function viewOf(state: typeof normalState, endings: EndingRow[]): GameView {
  return {
    state,
    scene: {
      id: "s01_village",
      text: "晨光初照，两界山遥遥在望。山下小村炊烟未散，师徒一行在此歇脚：前路乏粮，再往西便是虎狼之地。",
    },
    choices: [
      {
        id: "c_take_rations",
        text: "向村家化些干粮",
        locked: false,
        missing: [],
        denial: null,
      },
    ],
    endings,
    chapters: [{ id: "ch01", title: "第一回 两界山前", locked: false }],
  };
}

const normalView: GameView = viewOf(normalState, []);

function overState(endingId: string, endingTitle: string) {
  return {
    ...normalState,
    flags: [endingId === "turned_back" ? "went_long_way" : "struck_without_evidence"],
    current_scene: endingId === "turned_back" ? "s01_cliff" : "s02_exposed",
    game_over: true,
    ending: { id: endingId, title: endingTitle },
  };
}

const turnedBackView: GameView = viewOf(
  overState("turned_back", "半途折返"),
  endingRows("turned_back"),
);
const banishedView: GameView = viewOf(
  overState("banished_early", "被逐早终"),
  endingRows("banished_early"),
);

const created: CreatedGame = { id: "game-1", state: normalState };
const created2: CreatedGame = { id: "game-2", state: normalState };

/** 假时钟下推进 0ms：冲刷挂起的微任务（mock promise 链），让视图落定。 */
async function flushMicrotasks() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

/** 取标题所在结局卡片（li）。 */
function cardByTitle(title: string): Element | null {
  return screen.getByText(title).closest("li");
}

function readStore(): unknown {
  const raw = window.localStorage.getItem("htextrpg-endings");
  return raw === null ? null : JSON.parse(raw);
}

describe("结局图态（App 级：game_over → EndingView）", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.mocked(createGame).mockReset();
    vi.mocked(getGame).mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("game_over 后渲染结局图：本局结局点亮并写 localStorage", async () => {
    vi.useFakeTimers();
    vi.mocked(createGame).mockResolvedValue(created);
    // 调用序：JourneyView 挂载读局（普通态）→ App 轮询读局（终局态）
    vi.mocked(getGame).mockResolvedValueOnce(normalView).mockResolvedValueOnce(turnedBackView);

    render(<App />);
    fireEvent.change(screen.getByLabelText("名号"), { target: { value: "悟空" } });
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    await flushMicrotasks();
    expect(screen.getByRole("button", { name: "向村家化些干粮" })).toBeInTheDocument();

    // 轮询 tick（2s）读到 game_over → 切结局图
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(screen.getByRole("button", { name: "再入轮回" })).toBeInTheDocument();
    expect(cardByTitle("半途折返")).toHaveClass("ending-lit");
    expect(screen.getByText("已见证")).toBeInTheDocument();
    expect(cardByTitle("现形归真")).not.toHaveClass("ending-lit");
    expect(readStore()).toEqual(["turned_back"]);
  });

  it("跨局合并：重开一局到达另一结局 → 两枚点亮", async () => {
    vi.useFakeTimers();
    vi.mocked(createGame).mockResolvedValueOnce(created).mockResolvedValueOnce(created2);
    vi.mocked(getGame)
      // 第一局：挂载普通态 → 轮询终局（半途折返）
      .mockResolvedValueOnce(normalView)
      .mockResolvedValueOnce(turnedBackView)
      // 第二局：挂载普通态 → 轮询终局（被逐早终）
      .mockResolvedValueOnce(normalView)
      .mockResolvedValueOnce(banishedView);

    render(<App />);
    fireEvent.change(screen.getByLabelText("名号"), { target: { value: "悟空" } });
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    await flushMicrotasks();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(cardByTitle("半途折返")).toHaveClass("ending-lit");
    expect(readStore()).toEqual(["turned_back"]);

    // 再入轮回 → 回建局态（清会话、保留结局进度），重开一局
    fireEvent.click(screen.getByRole("button", { name: "再入轮回" }));
    await flushMicrotasks();
    fireEvent.change(screen.getByLabelText("名号"), { target: { value: "悟能" } });
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    await flushMicrotasks();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(cardByTitle("半途折返")).toHaveClass("ending-lit");
    expect(cardByTitle("被逐早终")).toHaveClass("ending-lit");
    expect(cardByTitle("现形归真")).not.toHaveClass("ending-lit");
    expect(cardByTitle("借扇西行")).not.toHaveClass("ending-lit");
    expect(readStore()).toEqual(["turned_back", "banished_early"]);
  });
});

describe("结局图态（EndingView 单元：缺失链与降级）", () => {
  const onRestart = vi.fn();

  beforeEach(() => {
    window.localStorage.clear();
    onRestart.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("未达结局渲染缺失条件链（不点亮）", () => {
    render(
      <EndingView
        endings={endingRows(null)}
        currentEnding={null}
        onRestart={onRestart}
      />,
    );
    const trueForm = within(cardByTitle("现形归真") as HTMLElement);
    expect(trueForm.getAllByText("缺失类型：flag")).toHaveLength(2);
    expect(
      trueForm.getByText("缺失项：旗标 bone_spirit_exposed（现有 false，需 true）"),
    ).toBeInTheDocument();
    expect(
      trueForm.getByText("缺失项：旗标 true_fan（现有 false，需 true）"),
    ).toBeInTheDocument();
    const westWon = within(cardByTitle("借扇西行") as HTMLElement);
    expect(
      westWon.getByText("缺失项：物品 banana_leaf_fan（现有 0，需 1）"),
    ).toBeInTheDocument();
    expect(screen.queryByText("已见证")).not.toBeInTheDocument();
    expect(cardByTitle("现形归真")).not.toHaveClass("ending-lit");
    expect(onRestart).not.toHaveBeenCalled();
  });

  it("localStorage 读失败（throw）→ 页面照常渲染，全灰", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied");
    });
    render(
      <EndingView
        endings={endingRows(null)}
        currentEnding={{ id: "west_won", title: "借扇西行" }}
        onRestart={onRestart}
      />,
    );
    expect(screen.getByRole("button", { name: "再入轮回" })).toBeInTheDocument();
    expect(cardByTitle("借扇西行")).not.toHaveClass("ending-lit");
    expect(cardByTitle("半途折返")).not.toHaveClass("ending-lit");
    expect(screen.queryByText("已见证")).not.toBeInTheDocument();
  });
});
