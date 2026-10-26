export function Pagination({
  page,
  more,
  onPage,
  size,
  onSize,
}: {
  page: number;
  more: boolean;
  onPage: (p: number) => void;
  size?: number;
  onSize?: (n: number) => void;
}) {
  return (
    <div className="pagination">
      <button disabled={page === 1} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <span>Page {page}</span>
      <button disabled={!more} onClick={() => onPage(page + 1)}>
        Next
      </button>
      {onSize && (
        <label>
          Rows per page{" "}
          <select value={size} onChange={(e) => onSize(Number(e.target.value))}>
            {[1, 10, 20, 50].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
