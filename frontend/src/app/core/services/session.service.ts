import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { CreateSessionResponse, SessionStatus } from '../models/session.model';
import { FinalReport } from '../models/report.model';

@Injectable({ providedIn: 'root' })
export class SessionService {
  constructor(private http: HttpClient) {}

  createSession(
    file: File,
    maxIterations: number,
    accuracyTarget: number,
    language: string
  ): Observable<CreateSessionResponse> {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('max_iterations', String(maxIterations));
    fd.append('accuracy_target', String(accuracyTarget));
    fd.append('language', language);
    return this.http.post<CreateSessionResponse>('/api/sessions', fd);
  }

  getSession(sessionId: string): Observable<SessionStatus> {
    return this.http.get<SessionStatus>(`/api/sessions/${sessionId}`);
  }

  submitDescriptions(sessionId: string, descriptions: Record<string, string>): Observable<{ status: string }> {
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
