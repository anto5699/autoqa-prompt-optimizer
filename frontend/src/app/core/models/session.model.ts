export interface ModelConfig {
  model: string;
  apiKey: string;
  baseUrl: string;
}

export interface ModelConfigValidateResponse {
  valid: boolean;
  model_used?: string | null;
  error?: string | null;
  models?: string[] | null;
}

export interface ParameterInfo {
  parameter_name: string;
  has_na: boolean;
}

export interface MetricConfig {
  type: 'static' | 'dynamic';
  answer_description: string;
  trigger_description?: string;
  trigger_speaker?: 'agent' | 'customer';
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
  parameters_detected: ParameterInfo[];
  excluded_parameters: string[];
  conversation_count: number;
}

export interface SessionStatus {
  session_id: string;
  current_phase: string;
  current_iteration: number;
  parameters: ParameterInfo[];
  clarifying_questions: ClarifyingQuestion[];
  parameter_summary: Record<string, ParameterSummary>;
  progress_log: string[];
  error_message?: string;
}

export interface ContinueResponse {
  new_session_id: string;
  parameters_continuing: string[];
}
