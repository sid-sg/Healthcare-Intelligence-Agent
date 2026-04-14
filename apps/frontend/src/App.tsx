import { useState, useRef, useEffect, useCallback } from "react";
import {
  Sparkles,
  Stethoscope,
  Building2,
  HeartPulse,
} from "lucide-react";
import type { ChatMessage } from "./types";
import { sendMessage } from "./api";
import ChatInput from "./components/ChatInput";
import MessageBubble from "./components/MessageBubble";
import FacilitiesMap from "./components/FacilitiesMap";
import type { Facility } from "./components/FacilitiesMap";
import "./App.css";

const EXAMPLE_QUERIES = [
  {
    text: "How many hospitals in Accra have the ability to perform dentistry?",
    icon: <Building2 size={15} />,
  },
  {
    text: "Which hospitals in Accra have cardiology?",
    icon: <HeartPulse size={15} />,
  },
  {
    text: "How many hospitals for cardiology are within 100 km of Accra?",
    icon: <Building2 size={15} />,
  },
  {
    text: "Which facilities claim to offer neurosurgery but lack the basic equipment required to perform it?",
    icon: <Stethoscope size={15} />,
  }
];

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [mapFacilities, setMapFacilities] = useState<Facility[] | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMsg: ChatMessage = {
      id: generateId(),
      role: "user",
      content: trimmed,
      timestamp: new Date(),
    };

    const loadingMsg: ChatMessage = {
      id: generateId(),
      role: "agent",
      content: "",
      timestamp: new Date(),
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setInput("");
    setIsLoading(true);

    // Create a new AbortController for this request
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await sendMessage(trimmed, "frontend-user-session", controller.signal);

      const agentMsg: ChatMessage = {
        id: loadingMsg.id,
        role: "agent",
        content: response.answer,
        steps: response.steps,
        citations: response.citations,
        extracted_citations: response.extracted_citations,
        mappable_facilities: response.mappable_facilities,
        timestamp: new Date(),
      };

      setMessages((prev) =>
        prev.map((m) => (m.id === loadingMsg.id ? agentMsg : m))
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        // User cancelled — replace loading bubble with a notice
        const cancelledMsg: ChatMessage = {
          id: loadingMsg.id,
          role: "agent",
          content: "*Response was stopped.*",
          timestamp: new Date(),
        };
        setMessages((prev) =>
          prev.map((m) => (m.id === loadingMsg.id ? cancelledMsg : m))
        );
      } else {
        const errorMsg: ChatMessage = {
          id: loadingMsg.id,
          role: "agent",
          content: `Sorry, something went wrong. ${error instanceof Error ? error.message : "Please try again."}`,
          timestamp: new Date(),
        };
        setMessages((prev) =>
          prev.map((m) => (m.id === loadingMsg.id ? errorMsg : m))
        );
      }
    } finally {
      abortControllerRef.current = null;
      setIsLoading(false);
    }
  };

  const handleStop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  const handleExampleClick = (query: string) => {
    setInput(query);
  };

  const handleShowMap = useCallback((facilities: any[]) => {
    // Filter to only facilities with valid lat/lon
    const valid = facilities.filter(
      (f: any) => f.lat != null && f.lon != null && !isNaN(f.lat) && !isNaN(f.lon)
    ) as Facility[];
    if (valid.length > 0) {
      setMapFacilities(valid);
    }
  }, []);

  const handleCloseMap = useCallback(() => {
    setMapFacilities(null);
  }, []);

  const showWelcome = messages.length === 0;
  const mapOpen = mapFacilities !== null && mapFacilities.length > 0;

  return (
    <div className="flex flex-col h-screen bg-[var(--color-bg-primary)]">
      {/* Header — full width */}
      <header className="flex-shrink-0 border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]/80 backdrop-blur-md z-20">
        <div className="px-6 py-3.5 flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-[var(--color-accent)] to-purple-500 shadow-[0_0_16px_var(--color-accent-glow)]">
            <Sparkles size={18} className="text-white" />
          </div>
          <div>
            <h1 className="text-[0.95rem] font-semibold text-[var(--color-text-primary)] leading-tight">
              Healthcare Intelligence Agent
            </h1>
            <p className="text-[0.7rem] text-[var(--color-text-muted)]">
              Powered by Databricks
            </p>
          </div>
        </div>
      </header>

      {/* Main content — split layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Chat panel */}
        <div
          className={`flex flex-col transition-all duration-300 ease-in-out ${mapOpen ? "w-1/2 border-r border-[var(--color-border)]" : "w-full"
            }`}
        >
          {/* Chat messages */}
          <div ref={chatContainerRef} className="flex-1 overflow-y-auto">
            <div className={`mx-auto px-4 py-6 ${mapOpen ? "max-w-2xl" : "max-w-4xl"}`}>
              {showWelcome ? (
                <WelcomeScreen onExampleClick={handleExampleClick} />
              ) : (
                <div className="space-y-6">
                  {messages.map((msg) => (
                    <MessageBubble
                      key={msg.id}
                      message={msg}
                      onShowMap={handleShowMap}
                    />
                  ))}
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input area */}
          <div className="flex-shrink-0 border-t border-[var(--color-border)] bg-[var(--color-bg-secondary)]/60 backdrop-blur-md">
            <div className={`mx-auto px-4 py-4 ${mapOpen ? "max-w-2xl" : "max-w-4xl"}`}>
              <ChatInput
                value={input}
                onChange={setInput}
                onSend={handleSend}
                isLoading={isLoading}
                onStop={handleStop}
              />
              <p className="text-center text-[0.65rem] text-[var(--color-text-muted)] mt-2.5">
                AI can make mistakes. Verify critical healthcare information with
                official sources.
              </p>
            </div>
          </div>
        </div>

        {/* Map panel — slides in from right */}
        {mapOpen && (
          <div className="w-1/2 animate-fade-in">
            <FacilitiesMap
              facilities={mapFacilities}
              onClose={handleCloseMap}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Welcome Screen ───────────────────────────────────────────────

function WelcomeScreen({
  onExampleClick,
}: {
  onExampleClick: (query: string) => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] animate-fade-in">
      {/* Logo + Title */}
      <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-[var(--color-accent)] to-purple-500 shadow-[0_0_40px_var(--color-accent-glow)] mb-6">
        <Sparkles size={28} className="text-white" />
      </div>
      <h2 className="text-2xl font-bold gradient-text mb-2">
        Healthcare Intelligence Agent
      </h2>
      <p className="text-[var(--color-text-secondary)] text-[0.9rem] mb-10 text-center max-w-md">
        Ask me about healthcare facilities across Ghana — services, locations,
        specializations, and more.
      </p>

      {/* Example queries */}
      <div className="w-full max-w-lg">
        <p className="text-[0.72rem] uppercase tracking-wider text-[var(--color-text-muted)] font-medium mb-3 text-center">
          Try asking
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {EXAMPLE_QUERIES.map((example) => (
            <button
              key={example.text}
              onClick={() => onExampleClick(example.text)}
              className="group flex items-center gap-2.5 px-4 py-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-hover)] hover:border-[var(--color-accent)] transition-all duration-200 text-left cursor-pointer"
            >
              <span className="text-[var(--color-text-muted)] group-hover:text-[var(--color-accent)] transition-colors">
                {example.icon}
              </span>
              <span className="text-[0.82rem] text-[var(--color-text-secondary)] group-hover:text-[var(--color-text-primary)] transition-colors">
                {example.text}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
