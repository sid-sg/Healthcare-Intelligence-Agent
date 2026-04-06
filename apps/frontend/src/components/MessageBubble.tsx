import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User, Bot } from "lucide-react";
import type { ChatMessage } from "../types";
import StepsAccordion from "./StepsAccordion";
import CitationsPanel from "./CitationsPanel";

interface MessageBubbleProps {
  message: ChatMessage;
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 py-2 px-1">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </div>
  );
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={`flex gap-3 animate-fade-in-up ${isUser ? "flex-row-reverse" : ""}`}
    >
      {/* Avatar */}
      <div
        className={`flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-xl mt-1 ${
          isUser
            ? "bg-[var(--color-accent)] shadow-[0_0_12px_var(--color-accent-glow)]"
            : "bg-gradient-to-br from-[var(--color-bg-tertiary)] to-[var(--color-bg-secondary)] border border-[var(--color-border)]"
        }`}
      >
        {isUser ? (
          <User size={16} className="text-white" />
        ) : (
          <Bot size={16} className="text-[var(--color-accent)]" />
        )}
      </div>

      {/* Message content */}
      <div className={`max-w-[80%] min-w-0 ${isUser ? "items-end" : ""}`}>
        {/* Sender label */}
        <p
          className={`text-[0.7rem] font-medium uppercase tracking-wider mb-1.5 ${
            isUser
              ? "text-right text-[var(--color-accent)]"
              : "text-[var(--color-text-muted)]"
          }`}
        >
          {isUser ? "You" : "Healthcare Agent"}
        </p>

        {/* Bubble */}
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? "bg-[var(--color-bg-user-msg)] border border-[rgba(74,108,247,0.2)] rounded-tr-md"
              : "bg-[var(--color-bg-agent-msg)] border border-[var(--color-border)] rounded-tl-md"
          }`}
        >
          {message.isLoading ? (
            <TypingIndicator />
          ) : (
            <>
              {/* Answer */}
              <div className="markdown-content text-[0.9rem] leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.content}
                </ReactMarkdown>
              </div>

              {/* Steps accordion */}
              {!isUser && message.steps && message.steps.length > 0 && (
                <StepsAccordion steps={message.steps} />
              )}

              {/* Citations */}
              {!isUser &&
                message.citations &&
                message.citations.length > 0 && (
                  <CitationsPanel citations={message.citations} />
                )}
            </>
          )}
        </div>

        {/* Timestamp */}
        <p
          className={`text-[0.65rem] text-[var(--color-text-muted)] mt-1 ${
            isUser ? "text-right" : ""
          }`}
        >
          {message.timestamp.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>
    </div>
  );
}
