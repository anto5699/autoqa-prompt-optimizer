export interface ModelConfig {
  model: string;
  apiKey: string;
  baseUrl: string;
  optimizerModel: string;
  useCustomOptimizerEndpoint: boolean;
  optimizerApiKey: string;
  optimizerBaseUrl: string;
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
  version?: 'v1' | 'v2';
  answer_description: string;
  trigger_description?: string;
  trigger_speaker?: 'agent' | 'customer';
  evaluation_type?: 'entire' | 'first' | 'last';
  n_messages?: number;
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
  rca_findings?: string;
}

export interface CreateSessionResponse {
  session_id: string;
  parameters_detected: ParameterInfo[];
  excluded_parameters: string[];
  conversation_count: number;
}

export interface NodeProgress {
  node: string;
  step: number;
  total: number;
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
  node_progress?: NodeProgress;
}

export interface ContinueResponse {
  new_session_id: string;
  parameters_continuing: string[];
}
