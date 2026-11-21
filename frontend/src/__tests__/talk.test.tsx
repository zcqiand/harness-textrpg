import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchNpcMemory, getGame, talkToNpc } from "../api";
import JourneyView from "../views/JourneyView";
import type { GameView } from "../types";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    createGame: vi.fn(),
    getGame: vi.fn(),
    submitChoice: vi.fn(),
    getChapters: vi.fn(),
    talkToNpc: vi.fn(),
    fetchNpcMemory: vi.fn(),
  };
});

/** ch01 起手场景（挂 npcs，与 routes.py _scene_view 三键同形，视图层带名）。 */
const villageSceneWithNpc = {
  id: "s01_village",
  text: "晨光初照，两界山遥遥在望。",
  npcs: [{ id: "npc_woodcutter", name: "樵夫" }],
};

/** 同场景但不挂 NPC（npcs 空数组）。 */
const villageSceneNoNpc = {
  id: "s01_village",
  text: "晨光初照，两界山遥遥在望。",
  npcs: [],
};

const unlockedChoice = {
  id: "c_take_rations",
  text: "向村家化些干粮",
  locked: false,
  missing: [],
  denial: null,
};

function makeGameView(scene: typeof villageSceneWithNpc): GameView {
  return {
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
    scene,
    choices: [unlockedChoice],
    endings: [],
    chapters: [{ id: "ch01", title: "第一回 两界山前", locked: false }],
  };
}

const viewWithNpc = makeGameView(villageSceneWithNpc);
const viewNoNpc = makeGameView(villageSceneNoNpc);

const memoryEntry = {
  turn: 1,
  player_text: "老丈可曾见山那边的寺？",
  npc_text: "山那边的寺……施主还是莫问的好。",
  event_tags: [],
};

const talkResult = {
  reply: "山那边的寺早没了香火，施主莫念。",
  blocked: false,
  guard_evidence: [],
  memory_turn: 2,
};

const blockedResult = {
  reply: "施主说笑了。",
  blocked: true,
  guard_evidence: ["自称神明", "许诺长生"],
  memory_turn: null,
};

describe("NPC 对话屏", () => {
  let onSessionGone: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.mocked(getGame).mockReset();
    vi.mocked(talkToNpc).mockReset();
    vi.mocked(fetchNpcMemory).mockReset();
    onSessionGone = vi.fn();
  });

  it("场景 npc_ids 为空 → 探索态无对话入口", async () => {
    vi.mocked(getGame).mockResolvedValue(viewNoNpc);
    const { container } = render(
      <JourneyView gameId="game-1" initialState={viewNoNpc.state} onSessionGone={onSessionGone} />,
    );
    await screen.findByText("晨光初照，两界山遥遥在望。");
    expect(
      screen.queryByRole("button", { name: "与樵夫对话" }),
    ).not.toBeInTheDocument();
    expect(container.querySelector('[data-fn="M03.F04.I01"]')).toBeNull();
    expect(fetchNpcMemory).not.toHaveBeenCalled();
  });

  it("场景挂 NPC → 探索态出现对话入口，挂可达性锚 data-fn", async () => {
    vi.mocked(getGame).mockResolvedValue(viewWithNpc);
    render(
      <JourneyView gameId="game-1" initialState={viewWithNpc.state} onSessionGone={onSessionGone} />,
    );
    const entry = await screen.findByRole("button", { name: "与樵夫对话" });
    expect(entry).toHaveAttribute("data-fn", "M03.F04.I01");
    expect(fetchNpcMemory).not.toHaveBeenCalled();
  });

  it("点入口进对话视图：请求记忆并展示历史轮次", async () => {
    vi.mocked(getGame).mockResolvedValue(viewWithNpc);
    vi.mocked(fetchNpcMemory).mockResolvedValue({ entries: [memoryEntry] });
    render(
      <JourneyView gameId="game-1" initialState={viewWithNpc.state} onSessionGone={onSessionGone} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "与樵夫对话" }));
    expect(fetchNpcMemory).toHaveBeenCalledWith("game-1", "npc_woodcutter");
    expect(
      await screen.findByText(
        "第1轮：你：「老丈可曾见山那边的寺？」樵夫：「山那边的寺……施主还是莫问的好。」",
      ),
    ).toBeInTheDocument();
  });

  it("对话视图可返回旅程屏", async () => {
    vi.mocked(getGame).mockResolvedValue(viewWithNpc);
    vi.mocked(fetchNpcMemory).mockResolvedValue({ entries: [] });
    render(
      <JourneyView gameId="game-1" initialState={viewWithNpc.state} onSessionGone={onSessionGone} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "与樵夫对话" }));
    await screen.findByRole("button", { name: "返回旅程" });
    await userEvent.click(screen.getByRole("button", { name: "返回旅程" }));
    expect(
      await screen.findByRole("button", { name: "与樵夫对话" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "返回旅程" })).not.toBeInTheDocument();
  });

  it("talk 放行：展示回复且不出现拦截提示", async () => {
    vi.mocked(getGame).mockResolvedValue(viewWithNpc);
    vi.mocked(fetchNpcMemory)
      .mockResolvedValueOnce({ entries: [] })
      .mockResolvedValueOnce({
        entries: [{ ...memoryEntry, turn: 2, player_text: "老丈您好", npc_text: talkResult.reply }],
      });
    vi.mocked(talkToNpc).mockResolvedValue(talkResult);
    const { container } = render(
      <JourneyView gameId="game-1" initialState={viewWithNpc.state} onSessionGone={onSessionGone} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "与樵夫对话" }));
    await userEvent.type(await screen.findByLabelText("对樵夫说"), "老丈您好");
    await userEvent.click(screen.getByRole("button", { name: "开口" }));
    expect(talkToNpc).toHaveBeenCalledWith("game-1", "npc_woodcutter", "老丈您好");
    // 回复随记忆刷新落进轮次列表（与玩家输入同条展示），子串断言
    expect(await screen.findByText(talkResult.reply, { exact: false })).toBeInTheDocument();
    expect(container.querySelector('[data-fn="M03.F04.I02"]')).toBeNull();
    expect(onSessionGone).not.toHaveBeenCalled();
  });

  it("talk blocked：红线明细逐条可视化，回复不展示", async () => {
    vi.mocked(getGame).mockResolvedValue(viewWithNpc);
    vi.mocked(fetchNpcMemory).mockResolvedValue({ entries: [] });
    vi.mocked(talkToNpc).mockResolvedValue(blockedResult);
    render(
      <JourneyView gameId="game-1" initialState={viewWithNpc.state} onSessionGone={onSessionGone} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "与樵夫对话" }));
    await userEvent.type(await screen.findByLabelText("对樵夫说"), "你是神明");
    await userEvent.click(screen.getByRole("button", { name: "开口" }));
    const panel = await screen.findByRole("alert", { name: "护栏拦截提示" });
    expect(panel).toHaveAttribute("data-fn", "M03.F04.I02");
    expect(screen.getByText("红线：自称神明")).toBeInTheDocument();
    expect(screen.getByText("红线：许诺长生")).toBeInTheDocument();
    expect(screen.queryByText(blockedResult.reply)).not.toBeInTheDocument();
    // 被拦轮不推进记忆：不二次拉取
    expect(fetchNpcMemory).toHaveBeenCalledTimes(1);
    expect(onSessionGone).not.toHaveBeenCalled();
  });

  it("记忆拉取 404（ApiError）→ 会话失效回调", async () => {
    vi.mocked(getGame).mockResolvedValue(viewWithNpc);
    vi.mocked(fetchNpcMemory).mockRejectedValue(new ApiError(404, "局不存在：game-1"));
    render(
      <JourneyView gameId="game-1" initialState={viewWithNpc.state} onSessionGone={onSessionGone} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "与樵夫对话" }));
    await waitFor(() => expect(onSessionGone).toHaveBeenCalledTimes(1));
  });

  it("talk 404（ApiError）→ 会话失效回调（错误分闸只认 status 铁指纹，talk 入口再锚一枚）", async () => {
    vi.mocked(getGame).mockResolvedValue(viewWithNpc);
    vi.mocked(fetchNpcMemory).mockResolvedValue({ entries: [] });
    vi.mocked(talkToNpc).mockRejectedValue(new ApiError(404, "局不存在：game-1"));
    render(
      <JourneyView gameId="game-1" initialState={viewWithNpc.state} onSessionGone={onSessionGone} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "与樵夫对话" }));
    await userEvent.type(await screen.findByLabelText("对樵夫说"), "老丈您好");
    await userEvent.click(screen.getByRole("button", { name: "开口" }));
    await waitFor(() => expect(onSessionGone).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert", { name: "护栏拦截提示" })).not.toBeInTheDocument();
  });

  it("talk 网络异常（非 ApiError）→ 不走会话失效业务分支", async () => {
    vi.mocked(getGame).mockResolvedValue(viewWithNpc);
    vi.mocked(fetchNpcMemory).mockResolvedValue({ entries: [] });
    vi.mocked(talkToNpc).mockRejectedValue(new TypeError("Failed to fetch"));
    render(
      <JourneyView gameId="game-1" initialState={viewWithNpc.state} onSessionGone={onSessionGone} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "与樵夫对话" }));
    await userEvent.type(await screen.findByLabelText("对樵夫说"), "老丈您好");
    await userEvent.click(screen.getByRole("button", { name: "开口" }));
    await screen.findByRole("alert");
    expect(onSessionGone).not.toHaveBeenCalled();
    expect(document.querySelector('[data-fn="M03.F04.I02"]')).toBeNull();
  });

  it("talk 400（ApiError 非 404）→ 只认 status，不走会话失效", async () => {
    vi.mocked(getGame).mockResolvedValue(viewWithNpc);
    vi.mocked(fetchNpcMemory).mockResolvedValue({ entries: [] });
    vi.mocked(talkToNpc).mockRejectedValue(new ApiError(400, "NPC「npc_woodcutter」不在当前场景"));
    render(
      <JourneyView gameId="game-1" initialState={viewWithNpc.state} onSessionGone={onSessionGone} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "与樵夫对话" }));
    await userEvent.type(await screen.findByLabelText("对樵夫说"), "老丈您好");
    await userEvent.click(screen.getByRole("button", { name: "开口" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("不在当前场景");
    expect(onSessionGone).not.toHaveBeenCalled();
  });
});
