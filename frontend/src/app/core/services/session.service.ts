import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { CreateSessionResponse, MetricConfig, ModelConfig, SessionStatus } from '../models/session.model';
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
    }
    return this.http.post<CreateSessionResponse>('/api/sessions', fd);
  }

  validateModelConfig(config: ModelConfig): Observable<{ valid: boolean; model_used?: string; error?: string }> {
    return this.http.post<{ valid: boolean; model_used?: string; error?: string }>(
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
}
