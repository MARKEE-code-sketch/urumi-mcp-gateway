import { useState } from "react";
export function OneTimeValue({
  value,
  label,
  onDismiss,
}: {
  value: string;
  label: string;
  onDismiss: () => void;
}) {
  const [copy, setCopy] = useState("");
  return (
    <section aria-label={label} className="disclosure">
      <h2>{label}</h2>
      <p>
        Shown once. Share privately; leaving or refreshing discards this value.
      </p>
      <textarea
        aria-label={label + " value"}
        data-sensitive
        readOnly
        value={value}
      />
      <button
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(value);
            setCopy("Copied.");
          } catch {
            setCopy("Copy unavailable. Select the value and copy it manually.");
          }
        }}
      >
        Copy
      </button>
      <button onClick={onDismiss}>Dismiss</button>
      <p role="status">{copy}</p>
    </section>
  );
}
