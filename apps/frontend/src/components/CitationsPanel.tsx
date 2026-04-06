import { useState } from "react";
import { ChevronDown, ChevronRight, FileText, ExternalLink } from "lucide-react";
import type { Citation } from "../types";

interface CitationsPanelProps {
  citations: Citation[];
}

export default function CitationsPanel({ citations }: CitationsPanelProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!citations || citations.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        id="toggle-citations"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 text-[0.8rem] font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors cursor-pointer group"
      >
        {isOpen ? (
          <ChevronDown size={14} className="transition-transform" />
        ) : (
          <ChevronRight size={14} className="transition-transform" />
        )}
        <FileText size={13} className="text-[var(--color-success)] opacity-60 group-hover:opacity-100 transition-opacity" />
        <span>
          {citations.length} citation{citations.length !== 1 ? "s" : ""}
        </span>
      </button>

      {isOpen && (
        <div className="mt-3 space-y-2 animate-slide-down">
          {citations.map((citation, index) => (
            <div
              key={index}
              className="rounded-xl border border-[var(--color-citation-border)] bg-[var(--color-citation-bg)] p-3.5 hover:border-[var(--color-accent)] transition-colors"
            >
              <div className="flex items-start gap-2.5">
                <div className="flex items-center justify-center w-6 h-6 rounded-lg bg-[var(--color-step-icon-bg)] flex-shrink-0 mt-0.5">
                  <FileText size={13} className="text-[var(--color-accent)]" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-[0.85rem] font-medium text-[var(--color-text-primary)] truncate">
                      {citation.source}
                    </p>
                    {citation.url && (
                      <a
                        href={citation.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-shrink-0 text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] transition-colors"
                        aria-label={`Open ${citation.source}`}
                      >
                        <ExternalLink size={13} />
                      </a>
                    )}
                  </div>
                  {citation.content && (
                    <p className="mt-1.5 text-[0.8rem] text-[var(--color-text-secondary)] line-clamp-3 leading-relaxed">
                      {citation.content}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
