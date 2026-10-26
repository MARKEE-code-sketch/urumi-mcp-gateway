import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Chat } from "../src/pages/Chat";
import type { Api } from "../src/api";
import type { ChatReply } from "../src/types";

afterEach(cleanup);

const reply: ChatReply = {
  request_id: "private-request-id",
  state: "completed",
  answer: "A readable **answer**.",
  tool_calls: [],
};
function apiWith(chat = vi.fn().mockResolvedValue(reply)) {
  return { chat, servers: vi.fn().mockResolvedValue({ items: [{ id: "server-id", name: "Real server", enabled: true, status: "Unreachable" }], has_more: true, page: 1, per_page: 20 }) } as unknown as Api;
}

describe("chat interaction and truthful outcomes", () => {
  it("inserts prompt cards without sending, and shows actual server status and pagination", async () => {
    const api = apiWith();
    const onNavigate = vi.fn();
    render(<Chat api={api} pending={vi.fn()} onNavigate={onNavigate} />);
    await screen.findByText("Real server");
    expect(screen.getByText("Enabled · Unreachable")).toBeTruthy();
    expect(screen.getByText(/Showing the first 1 servers/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Connect the dots/ }));
    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toContain("inventory tools");
    expect(document.activeElement).toBe(screen.getByLabelText("Message"));
    expect(api.chat).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("link", { name: /View servers/ }));
    expect(onNavigate).toHaveBeenCalledWith("/servers");
  });

  it("prevents duplicate submissions while awaiting a single final response", async () => {
    let resolve!: (value: ChatReply) => void;
    const chat = vi.fn().mockImplementation(() => new Promise<ChatReply>((r) => { resolve = r; }));
    const pending = vi.fn();
    const { container } = render(<Chat api={apiWith(chat)} pending={pending} />);
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "  stock  " } });
    const form = container.querySelector("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(chat).toHaveBeenCalledExactlyOnceWith("stock");
    expect(screen.getByText(/Waiting for the final reply/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Send message" }) as HTMLButtonElement).disabled).toBe(true);
    resolve(reply);
    await screen.findByText("answer");
    expect(pending.mock.calls).toEqual([[true], [false]]);
    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("");
    expect(screen.getByText("private-request-id").closest("details")?.open).toBe(false);
  });

  it.each(["failed", "limit_reached"] as const)("keeps %s and uncertain tool warnings outside closed details", async (state) => {
    render(<Chat api={apiWith(vi.fn().mockResolvedValue({ ...reply, state, tool_calls: [{ call_id: "call-id", tool_name: "woocommerce__create_product", outcome: "timeout", server_id: null, audit_id: null, duration_ms: 5000 }] }))} pending={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Create a product" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    const warning = await screen.findByText(/Remote effects may have happened/);
    expect(warning.closest("details")).toBeNull();
    expect(screen.getByText(/tool attempt did not succeed/).closest("details")).toBeNull();
    expect(screen.getByText(state === "failed" ? /request did not complete successfully/ : /request reached its execution limit/).closest("details")).toBeNull();
  });

  it("keeps at most ten independent exchanges during the visit", async () => {
    const { container } = render(<Chat api={apiWith()} pending={vi.fn()} />);
    for (let index = 0; index < 11; index++) {
      fireEvent.change(screen.getByLabelText("Message"), { target: { value: `Question ${index}` } });
      fireEvent.click(screen.getByRole("button", { name: "Send message" }));
      await waitFor(() => expect((screen.getByRole("button", { name: "Send message" }) as HTMLButtonElement).disabled).toBe(false));
    }
    expect(container.querySelectorAll("article.exchange")).toHaveLength(10);
    expect(screen.queryByText("Question 0")).toBeNull();
    expect(screen.getByText(/oldest exchange was discarded/)).toBeTruthy();
  });
});
