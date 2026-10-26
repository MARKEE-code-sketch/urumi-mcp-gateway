import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api";
export function Feedback({
  error,
  loading = false,
}: {
  error?: unknown;
  loading?: boolean;
}) {
  return (
    <>
      {loading && <p role="status">Loading...</p>}
      {error && (
        <div role="alert">
          <p>
            {error instanceof Error
              ? error.message
              : "The request could not be completed."}
          </p>
          {error instanceof ApiError && error.requestId && (
            <p>Request ID: {error.requestId}</p>
          )}
          {error instanceof ApiError && error.uncertain && (
            <p>
              The response was lost. The change may have happened. Refresh the
              list before trying again. For possible tool effects, inspect
              Audit.
            </p>
          )}
        </div>
      )}
    </>
  );
}
export function useRead<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T>(),
    [error, setError] = useState<unknown>(),
    [loading, setLoading] = useState(true),
    [refresh, setRefresh] = useState(0);
  const sequence = useRef(0);
  useEffect(() => {
    const current = ++sequence.current;
    setData(undefined);
    setError(undefined);
    setLoading(true);
    Promise.resolve()
      .then(load)
      .then((value) => {
        if (current === sequence.current) setData(value);
      })
      .catch((e) => {
        if (current === sequence.current) setError(e);
      })
      .finally(() => {
        if (current === sequence.current) setLoading(false);
      });
    return () => {
      sequence.current++;
    };
  }, [...deps, refresh]);
  return { data, error, loading, reload: () => setRefresh((v) => v + 1) };
}
export function utc(value: string | null | undefined) {
  return value ? (
    <span title={"Exact UTC: " + value}>
      {new Intl.DateTimeFormat("en-IN", {
        dateStyle: "medium",
        timeStyle: "medium",
        timeZone: "Asia/Kolkata",
      }).format(new Date(value))}{" "}
      Asia/Kolkata <small>({value} UTC)</small>
    </span>
  ) : (
    "Unknown"
  );
}
