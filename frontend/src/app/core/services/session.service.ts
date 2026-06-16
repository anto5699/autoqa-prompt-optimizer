import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ContinueResponse, CreateSessionResponse, MetricConfig, ModelConfig, ModelConfigValidateResponse, SessionStatus } from '../models/session.model';
import { FinalReport } from '../models/report.model';

@Injectable({ providedIn: 'root' })
export class SessionService {
  constructor(private http: HttpClient) {}

  createSession(
    file: File,
    maxIterations: number,
    accuracyTarget: number,
    language: string,
    modelConfig?: ModelConfig
  ): Observable<CreateSessionResponse> {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('max_iterations', String(maxIterations));
    fd.append('accuracy_target', String(accuracyTarget));
    fd.append('language', language);
    if (modelConfig) {
      fd.append('model_name', modelConfig.model);
      fd.append('api_key_override', modelConfig.apiKey);
      fd.append('base_url', modelConfig.baseUrl);
      if (modelConfig.optimizerModel) fd.append('optimizer_model_name', modelConfig.optimizerModel);
      if (modelConfig.useCustomOptimizerEndpoint) {
        if (modelConfig.optimizerApiKey) fd.append('optimizer_api_key_override', modelConfig.optimizerApiKey);
        if (modelConfig.optimizerBaseUrl) fd.append('optimizer_base_url', modelConfig.optimizerBaseUrl);
      }
    }
    return this.http.post<CreateSessionResponse>('/api/sessions', fd);
  }

  validateModelConfig(config: ModelConfig): Observable<ModelConfigValidateResponse> {
    return this.http.post<ModelConfigValidateResponse>(
      '/api/config/validate',
      { model: config.model, api_key: config.apiKey, base_url: config.baseUrl }
    );
  }

  getSession(sessionId: string): Observable<SessionStatus> {
    return this.http.get<SessionStatus>(`/api/sessions/${sessionId}`);
  }

  submitDescriptions(sessionId: string, descriptions: Record<string, MetricConfig>): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`/api/sessions/${sessionId}/descriptions`, { descriptions });
  }

  submitAnswers(sessionId: string, answers: Record<string, string>): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`/api/sessions/${sessionId}/answers`, { answers });
  }

  getReport(sessionId: string): Observable<FinalReport> {
    return this.http.get<FinalReport>(`/api/sessions/${sessionId}/report`);
  }

  deleteSession(sessionId: string): Observable<void> {
    return this.http.delete<void>(`/api/sessions/${sessionId}`);
  }

  continueOptimization(sessionId: string, additionalIterations: number): Observable<ContinueResponse> {
    return this.http.post<ContinueResponse>(`/api/sessions/${sessionId}/continue`, {
      additional_iterations: additionalIterations,
    });
  }
}
