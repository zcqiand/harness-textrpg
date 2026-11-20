import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createGame, getGame } from "../api";
import App from "../App";
import type { CreatedGame, GameView } from "../types";

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

const createdGame: CreatedGame = {
  id: "game-1",
  state: {
    player_name: "悟空",
    flags: [],
    attributes: {},
    backpack: [],
    current_chapter: "ch01",
    current_scene: "s1",
    game_over: false,
    ending: null,
  },
};

const gameView: GameView = {
  state: createdGame.state,
  scene: {
    id: "s1",
    text: "山门前",
  },
  choices: [],
  endings: [],
  chapters: [{ id: "ch01", title: "第一回 两界山前", locked: false }],
};

describe("建局态", () => {
  beforeEach(() => {
    vi.mocked(createGame).mockReset();
    vi.mocked(getGame).mockReset();
  });

  it("输入名号点开始 → createGame 收到「悟空」并进入探索视图", async () => {
    vi.mocked(createGame).mockResolvedValue(createdGame);
    vi.mocked(getGame).mockResolvedValue(gameView);
    render(<App />);
    await userEvent.type(screen.getByLabelText("名号"), "悟空");
    await userEvent.click(screen.getByRole("button", { name: "开始" }));
    expect(createGame).toHaveBeenCalledWith("悟空");
    expect(await screen.findByText("第一回 两界山前")).toBeInTheDocument();
  });

  it("空名号不发起建局请求", async () => {
    vi.mocked(createGame).mockResolvedValue(createdGame);
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "开始" }));
    expect(createGame).not.toHaveBeenCalled();
    expect(screen.queryByText("第一回 两界山前")).not.toBeInTheDocument();
  });

  it("建局失败 → 错误文案可见，不进入探索视图", async () => {
    vi.mocked(createGame).mockRejectedValue(new Error("player_name 必填且不能为空白"));
    render(<App />);
    await userEvent.type(screen.getByLabelText("名号"), "八戒");
    await userEvent.click(screen.getByRole("button", { name: "开始" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "player_name 必填且不能为空白",
    );
    expect(screen.queryByText("第一回 两界山前")).not.toBeInTheDocument();
  });
});
