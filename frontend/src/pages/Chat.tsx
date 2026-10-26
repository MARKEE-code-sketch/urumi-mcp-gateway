import { useRef, useState } from "react";
import { Api, chatMessage } from "../api";
import type { ChatReply } from "../types";
import { Feedback, useRead } from "../components/Feedback";
import { ChatAnswer } from "../components/ChatAnswer";
import { Icon, type IconName } from "../components/Icon";
import mark from "../assets/urumi-mark.svg?no-inline";

const prompts: { title: string; description: string; message: string; icon: IconName; color: string }[] = [
  { title: "Explore your products", description: "Find products, prices and stock details.", message: "List our WooCommerce products with their IDs, SKUs and INR prices.", icon: "package", color: "peach" },
  { title: "Check today’s orders", description: "Get a clear picture of your latest orders.", message: "Show me today's WooCommerce orders.", icon: "orders", color: "lavender" },
  { title: "Connect the dots", description: "Bring product and inventory tools together.", message: "List our WooCommerce products and use the inventory tools to check their stock availability.", icon: "inventory", color: "mint" },
];

function Reply({ reply }: { reply: ChatReply }) {
  const unsuccessful = reply.tool_calls.filter((call) => call.outcome !== "success");
  const uncertain = reply.tool_calls.some((call) => ["unknown", "timeout"].includes(call.outcome));
  return (
    <div className="assistant-message">
      <div className="message-author">
        <img src={mark} alt="" width="28" height="28" />
        <strong>Urumi</strong>
        <span className={reply.state === "completed" ? "status green" : "status warning"}>
          {reply.state === "completed" ? "Completed" : reply.state === "limit_reached" ? "Limit reached" : "Failed"}
        </span>
      </div>
      {reply.state !== "completed" && <p className="chat-warning" role="status">{reply.state === "limit_reached" ? "The request reached its execution limit. The answer may be incomplete." : "The request did not complete successfully. Review the answer and tool activity before trying again."}</p>}
      {unsuccessful.length > 0 && <p className="chat-warning">{unsuccessful.length} tool attempt{unsuccessful.length === 1 ? "" : "s"} did not succeed: {unsuccessful.map((call) => `${call.tool_name} (${call.outcome})`).join(", ")}.</p>}
      {uncertain && <p className="chat-warning">Remote effects may have happened. Inspect Activity before another attempt.</p>}
      <ChatAnswer answer={reply.answer} />
      <details className="tool-activity">
        <summary><Icon name="audit" /><strong>{reply.tool_calls.length ? `${reply.tool_calls.length} tool attempt${reply.tool_calls.length === 1 ? "" : "s"}` : "No tool calls"}</strong><span className="subtle">{reply.tool_calls.filter((call) => call.outcome === "success").length} successful</span></summary>
        <div className="tool-activity-body">
          {reply.tool_calls.map((call) => <section key={call.call_id}>
            <div><strong>{call.tool_name}</strong><span className={call.outcome === "success" ? "status green" : "status warning"}>{call.outcome}</span></div>
            {(call.error_code || call.result_summary) && <p className="plain">{call.error_code} {call.result_summary}</p>}
          </section>)}
        </div>
      </details>
      <details className="request-details">
        <summary>Request details</summary>
        <dl><dt>Request</dt><dd>{reply.request_id}</dd><dt>Terminal state</dt><dd>{reply.state}</dd></dl>
        {reply.tool_calls.map((call) => <section key={call.call_id}>
          <h3>{call.tool_name}</h3>
          <dl><dt>Call</dt><dd>{call.call_id}</dd><dt>Server</dt><dd>{call.server_id ?? "Unknown"}</dd><dt>Duration (ms)</dt><dd>{call.duration_ms ?? "Unknown"}</dd><dt>Audit record</dt><dd>{call.audit_id ?? "Unknown"}</dd></dl>
        </section>)}
      </details>
    </div>
  );
}

export function Chat({ api, pending, onNavigate }: { api: Api; pending: (v: boolean) => void; onNavigate?: (path: string) => void }) {
  const [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(),
    [dropped, setDropped] = useState(false),
    [exchanges, setExchanges] = useState<{ message: string; reply: ChatReply }[]>([]);
  const submitting = useRef(false), composer = useRef<HTMLTextAreaElement>(null);
  const servers = useRead(() => api.servers(1, 20), [api]);
  const navigate = (event: React.MouseEvent<HTMLAnchorElement>, path: string) => {
    if (onNavigate && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && event.button === 0) {
      event.preventDefault();
      onNavigate(path);
    }
  };
  return (
    <section className="chat-page">
      <div className="conversation">
        {exchanges.length === 0 ? <div className="welcome">
          <div className="welcome-mark"><img src={mark} alt="" width="42" height="42" /></div>
          <span className="eyebrow">YOUR CONNECTED WORKSPACE</span>
          <h1 tabIndex={-1}>Less switching.<br />More getting things done.</h1>
          <p className="intro">Ask a question. Work across your tools.<br />Keep everything in one place.</p>
          <div className="prompts">{prompts.map((prompt) => <button key={prompt.title} type="button" className="prompt-card" disabled={busy} onClick={() => { setMessage(prompt.message); composer.current?.focus(); }}>
            <span className={`prompt-icon ${prompt.color}`}><Icon name={prompt.icon} /></span>
            <strong>{prompt.title}</strong><span>{prompt.description}</span><Icon name="arrow" className="card-arrow" />
          </button>)}</div>
        </div> : <div className="conversation-heading"><span className="eyebrow">YOUR WORKSPACE</span><h1 tabIndex={-1}>Chat</h1></div>}
        {exchanges.map((exchange, index) => <article className="exchange" key={index}>
          <div className="user-message"><div className="message-author"><strong>You</strong></div><p className="plain">{exchange.message}</p></div>
          <Reply reply={exchange.reply} />
        </article>)}
        {dropped && <p className="composer-note">The oldest exchange was discarded to keep this visit bounded.</p>}
        <div className="composer-area">
          <form className="composer" onSubmit={async (event) => {
            event.preventDefault();
            if (submitting.current) return;
            setError(undefined);
            try {
              const text = chatMessage(message);
              submitting.current = true;
              setBusy(true);
              pending(true);
              const reply = await api.chat(text);
              setExchanges((old) => {
                if (old.length >= 10) setDropped(true);
                return [...old, { message: text, reply }].slice(-10);
              });
              setMessage("");
            } catch (caught) {
              setError(caught);
            } finally {
              submitting.current = false;
              setBusy(false);
              pending(false);
            }
          }}>
            <label htmlFor="chat-message" className="sr-only">Message</label>
            <textarea id="chat-message" ref={composer} required value={message} disabled={busy} onChange={(event) => setMessage(event.target.value)} placeholder="What would you like to do?" rows={2} />
            <div className="composer-footer"><span><Icon name="servers" />Tools run with your permissions</span><button className="send-button" disabled={busy} aria-label="Send message"><Icon name="send" /></button></div>
          </form>
          <p className="composer-note">Each message is independent. This visit keeps at most 10 replies; no conversation is saved.</p>
          {busy && <p role="status">Waiting for the final reply. Tools may be running; leaving does not undo remote effects.</p>}
          <Feedback error={error} />
        </div>
      </div>
      <aside className="context" aria-label="Workspace context">
        <div className="context-heading"><span className="context-title">In this workspace</span></div>
        <div className="context-section">
          <div className="section-heading"><h2>Team servers</h2></div>
          <Feedback loading={servers.loading} error={servers.error} />
          {servers.data?.items.map((server) => <div className="connection" key={server.id}>
            <span className="integration-icon"><Icon name="servers" /></span><div><strong>{server.name}</strong><span>{server.enabled ? "Enabled" : "Disabled"} · {server.status}</span></div>
          </div>)}
          {servers.data && !servers.data.items.length && <p>No servers on this page.</p>}
          {servers.data?.has_more && <p className="subtle">Showing the first {servers.data.items.length} servers. More are available in Servers.</p>}
          {servers.data?.stale && <p className="chat-warning">Server information may be stale.</p>}
          {servers.data && <p className="subtle">Stored server status.</p>}
          <a className="text-link" href="/servers" onClick={(event) => navigate(event, "/servers")}>View servers <Icon name="arrow" /></a>
        </div>
        <div className="context-section how-it-works"><span className="guide-icon"><Icon name="shield" /></span><h2>A little clarity,<br />before you start.</h2><p>Urumi uses the tools available to you. You’ll see which tools were called alongside every answer.</p><div className="rule" /><span className="number-line"><b>01</b>Ask in plain language</span><span className="number-line"><b>02</b>Your tools do the work</span><span className="number-line"><b>03</b>Review the answer</span></div>
        <div className="context-footnote"><Icon name="audit" /><p>Tool calls are recorded in <a href="/audit" onClick={(event) => navigate(event, "/audit")}>Activity</a> for your team to review.</p></div>
      </aside>
    </section>
  );
}

