import { useState } from "react";
import { ChevronDown, ChevronRight, Wrench, Brain, BarChart3 } from "lucide-react";
import type { AgentStep } from "../types";

interface StepsAccordionProps {
  steps: AgentStep[];
}

function StepIcon({ type }: { type: string }) {
  switch (type) {
    case "tool_call":
      return <Wrench size={14} className="text-[var(--color-accent)]" />;
    case "tool_result":
      return <BarChart3 size={14} className="text-[var(--color-success)]" />;
    case "reasoning":
      return <Brain size={14} className="text-purple-400" />;
    default:
      return <Wrench size={14} className="text-[var(--color-text-muted)]" />;
  }
}

function ResultsTable({ results, maxRows = 10 }: { results: unknown; maxRows?: number }) {
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
      <div className="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-primary)] custom-scrollbar">
        <table className="w-full text-left text-[0.8rem] min-w-max">
          <thead className="bg-[var(--color-bg-tertiary)] text-[var(--color-text-primary)] border-b border-[var(--color-border)] uppercase tracking-wider text-[0.7rem]">
            <tr>
              {columns.map((col) => (
                <th key={col} className="px-3.5 py-2.5 font-semibold">
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

function StepContent({ step }: { step: AgentStep }) {
  const content = step.content;

  if (step.type === "reasoning" && content.thoughts) {
    return (
      <ul className="list-none space-y-1.5 text-[0.85rem] text-[var(--color-text-secondary)]">
        {(content.thoughts as string[]).map((thought, i) => (
          <li key={i} className="flex gap-2">
            <span className="text-purple-400 mt-0.5 flex-shrink-0">•</span>
            <span>{thought}</span>
          </li>
        ))}
      </ul>
    );
  }

  if (content.sql_query) {
    return (
      <div className="space-y-2">
        <div>
          <span className="text-[0.75rem] uppercase tracking-wider text-[var(--color-text-muted)] font-medium">
            SQL Query
          </span>
          <pre className="mt-1 rounded-lg bg-[var(--color-bg-primary)] border border-[var(--color-border)] p-3 text-[0.8rem] overflow-x-auto">
            <code className="text-[var(--color-info)]">{content.sql_query}</code>
          </pre>
        </div>
        
        {content.results ? <ResultsTable results={content.results} maxRows={10} /> : null}
        
        {content.tool_answer && (
          <p className="text-[0.85rem] text-[var(--color-text-secondary)] mt-2">
            <span className="font-medium text-[var(--color-text-primary)]">Result: </span>
            <span dangerouslySetInnerHTML={{ __html: String(content.tool_answer).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') }} />
          </p>
        )}
        
        {content.num_rows !== undefined && !content.results && (
          <p className="text-[0.8rem] text-[var(--color-text-muted)]">
            {content.num_rows} row{content.num_rows !== 1 ? "s" : ""} returned
          </p>
        )}
      </div>
    );
  }

  // Generic JSON content
  return (
    <pre className="rounded-lg bg-[var(--color-bg-primary)] border border-[var(--color-border)] p-3 text-[0.8rem] overflow-x-auto text-[var(--color-text-secondary)]">
      <code>{JSON.stringify(content, null, 2)}</code>
    </pre>
  );
}

export default function StepsAccordion({ steps }: StepsAccordionProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!steps || steps.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        id="toggle-steps"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 text-[0.8rem] font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors cursor-pointer group"
      >
        {isOpen ? (
          <ChevronDown size={14} className="transition-transform" />
        ) : (
          <ChevronRight size={14} className="transition-transform" />
        )}
        <Wrench size={13} className="text-[var(--color-accent)] opacity-60 group-hover:opacity-100 transition-opacity" />
        <span>
          {steps.length} step{steps.length !== 1 ? "s" : ""}
        </span>
      </button>

      {isOpen && (
        <div className="mt-3 space-y-2 animate-slide-down">
          {steps.map((step) => (
            <StepItem key={step.step_number} step={step} />
          ))}
        </div>
      )}
    </div>
  );
}

function StepItem({ step }: { step: AgentStep }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-[var(--color-border-step)] bg-[var(--color-bg-step)] overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-[var(--color-bg-hover)] transition-colors cursor-pointer"
      >
        <div className="flex items-center justify-center w-6 h-6 rounded-lg bg-[var(--color-step-icon-bg)]">
          <StepIcon type={step.type} />
        </div>
        <span className="text-[0.82rem] font-medium text-[var(--color-text-secondary)] flex-1">
          Step {step.step_number}: {step.title}
        </span>
        {expanded ? (
          <ChevronDown size={14} className="text-[var(--color-text-muted)]" />
        ) : (
          <ChevronRight size={14} className="text-[var(--color-text-muted)]" />
        )}
      </button>
      {expanded && (
        <div className="px-3.5 pb-3 pt-1 border-t border-[var(--color-border-step)] animate-slide-down">
          <StepContent step={step} />
        </div>
      )}
    </div>
  );
}
