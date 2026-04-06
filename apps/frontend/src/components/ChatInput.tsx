import { useRef, useEffect, type KeyboardEvent } from "react";
import { SendHorizonal } from "lucide-react";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
}

export default function ChatInput({
  value,
  onChange,
  onSend,
  disabled = false,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize the textarea as content grows
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [value]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !disabled) {
        onSend();
      }
    }
  };

  return (
    <div className="relative flex items-end gap-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-input)] px-4 py-3 transition-all duration-200 focus-within:border-[var(--color-border-focus)] focus-within:shadow-[0_0_0_3px_var(--color-accent-glow)]">
      <textarea
        ref={textareaRef}
        id="chat-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about Ghana healthcare facilities..."
        disabled={disabled}
        rows={1}
        className="flex-1 resize-none bg-transparent text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] outline-none text-[0.95rem] leading-relaxed max-h-[200px] min-h-[24px] disabled:opacity-50"
      />
      <button
        id="send-button"
        onClick={onSend}
        disabled={disabled || !value.trim()}
        className="flex-shrink-0 flex items-center justify-center w-9 h-9 rounded-xl bg-[var(--color-accent)] text-white transition-all duration-200 hover:bg-[var(--color-accent-hover)] hover:scale-105 active:scale-95 disabled:opacity-30 disabled:hover:scale-100 disabled:cursor-not-allowed cursor-pointer"
        aria-label="Send message"
      >
        <SendHorizonal size={18} />
      </button>
    </div>
  );
}
