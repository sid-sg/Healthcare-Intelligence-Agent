import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import ResultsTable from "./ResultsTable";

interface DataAccordionProps {
  title: string;
  icon: React.ReactNode;
  data: any[];
  maxRows?: number;
}

export default function DataAccordion({ title, icon, data, maxRows = 10 }: DataAccordionProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!data || data.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 text-[0.8rem] font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors cursor-pointer group"
      >
        {isOpen ? (
          <ChevronDown size={14} className="transition-transform" />
        ) : (
          <ChevronRight size={14} className="transition-transform" />
        )}
        <div className="text-[var(--color-accent)] opacity-60 group-hover:opacity-100 transition-opacity">
          {icon}
        </div>
        <span>
          {title} ({data.length})
        </span>
      </button>

      {isOpen && (
        <div className="mt-3 space-y-2 animate-slide-down border border-[var(--color-border-step)] bg-[var(--color-bg-step)] rounded-xl p-3 pt-1">
          <ResultsTable results={data} maxRows={maxRows} />
        </div>
      )}
    </div>
  );
}
