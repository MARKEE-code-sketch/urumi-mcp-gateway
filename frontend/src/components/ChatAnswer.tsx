import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

function safeLink(value: string) {
  if (!/^(https?:\/\/|mailto:)/i.test(value)) return "";
  try {
    const url = new URL(value);
    return ["https:", "http:", "mailto:"].includes(url.protocol) ? value : "";
  } catch {
    return "";
  }
}

function alignment(value: unknown) {
  return value === "left" || value === "center" || value === "right"
    ? `text-align-${value}` : undefined;
}

// Model text is untrusted: no HTML, images, automatic fetches or inline styles.
export function ChatAnswer({ answer }: { answer: string }) {
  return (
    <div className="markdown-answer">
      <Markdown remarkPlugins={[remarkGfm]} skipHtml urlTransform={safeLink}
        components={{
          img: () => null,
          a: ({ href, children }) => href ? <a href={href} rel="noreferrer">{children}</a> : <span>{children}</span>,
          table: ({ children }) => <div className="markdown-table-wrap" role="region" aria-label="Answer table" tabIndex={0}><table>{children}</table></div>,
          th: ({ node, children }) => <th className={alignment(node?.properties.align)} scope="col">{children}</th>,
          td: ({ node, children }) => <td className={alignment(node?.properties.align)}>{children}</td>,
        }}
      >{answer}</Markdown>
    </div>
  );
}
