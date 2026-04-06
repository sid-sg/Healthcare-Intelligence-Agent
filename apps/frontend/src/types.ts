export interface StepContent {
  sql_query?: string;
  results?: unknown;
  tool_answer?: string;
  num_rows?: number;
  thoughts?: string[];
  raw?: string;
  [key: string]: unknown;
}

export interface AgentStep {
  step_number: number;
  type: "tool_call" | "tool_result" | "reasoning";
  icon: string;
  title: string;
  content: StepContent;
}

export interface Citation {
  source: string;
  content: string;
  url: string;
}

export interface AgentResponse {
  answer: string;
  steps: AgentStep[];
  citations: Citation[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  content: string;
  steps?: AgentStep[];
  citations?: Citation[];
  timestamp: Date;
  isLoading?: boolean;
}
