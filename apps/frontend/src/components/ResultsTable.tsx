export default function ResultsTable({ results, maxRows = 10 }: { results: unknown; maxRows?: number }) {
  let data = results;
  if (typeof data === "string") {
    try {
      data = JSON.parse(data);
    } catch {
      return null;
    }
  }

  if (!Array.isArray(data) || data.length === 0) {
    return null;
  }

  if (typeof data[0] !== "object" || data[0] === null) {
    return null;
  }

  // Handle array of arrays vs array of objects
  let columns: string[] = [];
  let displayData: any[] = [];
  
  if (Array.isArray(data[0])) {
    // Some basic handling for array of arrays, assuming first row is not header
    columns = data[0].map((_, i) => `Col ${i + 1}`);
    displayData = data;
  } else {
    columns = Object.keys(data[0]);
    displayData = data;
  }

  if (columns.length === 0) return null;

  const showingData = displayData.slice(0, maxRows);
  const remaining = displayData.length - maxRows;

  return (
    <div className="mt-3 overflow-hidden">
      <div className="max-h-[250px] overflow-y-auto overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-primary)] custom-scrollbar">
        <table className="w-full text-left text-[0.8rem] min-w-max border-none">
          <thead className="text-[var(--color-text-primary)] uppercase tracking-wider text-[0.7rem]">
            <tr>
              {columns.map((col) => (
                <th key={col} className="sticky top-0 z-10 bg-[var(--color-bg-tertiary)] px-3.5 py-2.5 font-semibold shadow-[calc(var(--border-width,0)*-1)_1px_0_var(--color-border)] outline outline-1 outline-[var(--color-border)]">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)] text-[var(--color-text-secondary)]">
            {showingData.map((row, i) => (
              <tr key={i} className="hover:bg-[var(--color-bg-hover)] transition-colors">
                {columns.map((col) => (
                  <td key={col} className="px-3.5 py-2 whitespace-nowrap">
                    {String(Array.isArray(row) ? row[columns.indexOf(col)] : (row[col] ?? ""))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {remaining > 0 && (
        <p className="text-[0.75rem] text-[var(--color-text-muted)] mt-2 flex items-start gap-1.5 italic bg-[var(--color-bg-primary)] p-2 rounded-md border border-[var(--color-border-step)]">
          <span className="text-[var(--color-info)] font-bold mt-0.5">ℹ</span>
          <span>
            Showing {maxRows} of {displayData.length} rows. The remaining {remaining} rows are omitted to prevent the chat interface from becoming unreadable with large data payloads.
          </span>
        </p>
      )}
    </div>
  );
}
