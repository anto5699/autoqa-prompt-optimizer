import { Injectable, NgZone } from '@angular/core';
import { Observable } from 'rxjs';

export interface SseEvent {
  type: 'progress' | 'complete' | 'error';
  data: Record<string, unknown>;
}

@Injectable({ providedIn: 'root' })
export class SseService {
  constructor(private zone: NgZone) {}

  connect(sessionId: string): Observable<SseEvent> {
    return new Observable(observer => {
      const es = new EventSource(`/api/sessions/${sessionId}/stream`);

      const handle = (type: SseEvent['type']) => (e: MessageEvent) => {
        this.zone.run(() => {
          try { observer.next({ type, data: JSON.parse(e.data) }); }
          catch { observer.next({ type, data: { message: e.data } }); }
          if (type === 'complete' || type === 'error') {
            es.close();
            observer.complete();
          }
        });
      };

      es.addEventListener('progress', handle('progress'));
      es.addEventListener('complete', handle('complete'));
      es.addEventListener('error', handle('error'));
      es.onerror = () => this.zone.run(() => { observer.error(new Error('SSE connection failed')); es.close(); });

      return () => es.close();
    });
  }
}
