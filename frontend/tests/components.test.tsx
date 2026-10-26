import { describe, it, expect, vi, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { OneTimeValue } from "../src/components/OneTimeValue";
import { useRead } from "../src/components/Feedback";
import { Confirm } from "../src/components/Confirm";
afterEach(cleanup);
describe("private display and request lifecycle", () => {
  it("ignores old view resolution even when abort cannot stop delivery", async () => {
    let resolveOld!: (v: string) => void;
    const old = new Promise<string>((r) => (resolveOld = r));
    function View({ filter }: { filter: string }) {
      const r = useRead(
        () => (filter === "old" ? old : Promise.resolve("new result")),
        [filter],
      );
      return <p>{r.data ?? "Loading"}</p>;
    }
    const view = render(<View filter="old" />);
    view.rerender(<View filter="new" />);
    await screen.findByText("new result");
    resolveOld("private old result");
    await Promise.resolve();
    expect(screen.queryByText("private old result")).toBeNull();
  });
  it("copy failure provides manual copy without claiming success", async () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    const close = vi.fn();
    render(
      <OneTimeValue
        label="Private test"
        value="dummy-only"
        onDismiss={close}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await screen.findByText(/Copy unavailable/);
    expect(screen.queryByText("Copied.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(close).toHaveBeenCalledOnce();
  });
  it("confirmation focuses confirm and restores prior focus", () => {
    const old = document.createElement("button");
    document.body.append(old);
    old.focus();
    const r = render(
      <Confirm
        message="Remove demo?"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Confirm" }),
    );
    r.unmount();
    expect(document.activeElement).toBe(old);
    old.remove();
  });
});

it("converts a synchronous invalid filter into safe feedback", async () => {
  function View() {
    const r = useRead<string>(() => {
      throw new Error("Invalid identifier.");
    }, []);
    return <p>{r.error instanceof Error ? r.error.message : "Loading"}</p>;
  }
  render(<View />);
  await screen.findByText("Invalid identifier.");
});
