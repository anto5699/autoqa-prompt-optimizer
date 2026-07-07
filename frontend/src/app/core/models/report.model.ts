export interface ConfusionMatrix {
  tp: number;
  tn: number;
  fp: number;
  fn: number;
}

export interface IterationEntry {
  iteration: number;
  accuracy: number;
  description?: string;
}

export interface ConversationResult {
  conversation_id: string;
  ground_truth: string;
  prediction: string;
  correct: boolean | null;
}

export interface ParameterReport {
  status: string;
  original_description?: string;
  final_accuracy: number;
  final_precision: number;
  final_recall: number;
  final_f1: number;
  confusion_matrix: ConfusionMatrix;
  not_applicable_count: number;
  initial_prompt: string;
  initial_accuracy: number | null;
  final_prompt: string;
  optimization_notes?: string;
  iteration_history: IterationEntry[];
  rca_findings?: string;
  report_summary?: string;
  regression_warning?: { message: string };
  recommendations: string[];
  conversation_results: ConversationResult[];
  version?: string;
  pivot_approved?: boolean;
  pivot_info?: {
    reason: string;
    original_description: string;
  };
  pre_audit_result?: string;
}

export interface ReportSummary {
  total_parameters: number;
  parameters_meeting_target: number;
  parameters_below_target: number;
  overall_accuracy: number;
  overall_precision: number;
  overall_recall: number;
  total_iterations: number;
  total_conversations: number;
  accuracy_target: number;
  models_used?: { evaluator?: string; optimizer?: string };
}

export interface FinalReport {
  session_id: string;
  generated_at: string;
  summary: ReportSummary;
  parameters: Record<string, ParameterReport>;
}
