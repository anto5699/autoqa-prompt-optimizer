export interface RuleInfo {
  rule_id: string;
  rule_type: string;
  speaker: string;
  evaluation_type: string;
  n_messages: number;
}

export interface ClarifyingQuestion {
  question_id: string;
  parameter_name: string;
  question_text: string;
  rationale: string;
}

export interface ParameterSummary {
  accuracy: number;
  status: string;
}

export interface CreateSessionResponse {
  session_id: string;
  rules_detected: RuleInfo[];
  excluded_rules: string[];
  conversation_count: number;
}

export interface SessionStatus {
  session_id: string;
  current_phase: string;
  current_iteration: number;
  rules: RuleInfo[];
  clarifying_questions: ClarifyingQuestion[];
  parameter_summary: Record<string, ParameterSummary>;
  progress_log: string[];
}
