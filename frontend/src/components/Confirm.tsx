import { useEffect, useRef } from "react";
export function Confirm({
  message,
  onConfirm,
  onCancel,
}: {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const old = document.activeElement as HTMLElement;
    ref.current?.focus();
    return () => old?.focus();
  }, []);
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Confirm action"
      className="confirmation"
    >
      <p>{message}</p>
      <button ref={ref} onClick={onConfirm}>
        Confirm
      </button>
      <button onClick={onCancel}>Cancel</button>
    </div>
  );
}
