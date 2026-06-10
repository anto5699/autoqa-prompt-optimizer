import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { SessionService } from '../../core/services/session.service';
import { MetricConfig, ParameterInfo } from '../../core/models/session.model';

interface MetricState {
  type: 'static' | 'dynamic';
  answerDescription: string;
  triggerDescription: string;
}

@Component({
  selector: 'app-descriptions',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="page">
      <div class="page-header">
        <h1>Configure Evaluation Parameters</h1>
        <p>For each metric detected in your CSV, choose whether it is <strong>Static</strong> (always evaluated) or <strong>Dynamic</strong> (only evaluated when a specific scenario is present). Provide plain-language descriptions — the AI will refine them.</p>
      </div>

      <div *ngIf="loading" class="loading-msg">Loading parameters…</div>
      <div *ngIf="error" class="error-msg">{{ error }}</div>

      <div *ngFor="let param of parameters" class="param-card">
        <div class="param-header">
          <span class="param-name">{{ param.parameter_name }}</span>
          <div class="type-toggle">
            <button
              class="toggle-btn"
              [class.active]="metricStates[param.parameter_name]?.type === 'static'"
              (click)="setType(param.parameter_name, 'static')">
              Static
            </button>
            <button
              class="toggle-btn"
              [class.active]="metricStates[param.parameter_name]?.type === 'dynamic'"
              (click)="setType(param.parameter_name, 'dynamic')">
              Dynamic
            </button>
          </div>
          <span *ngIf="param.has_na" class="na-badge">NA detected → Dynamic</span>
        </div>

        <ng-container *ngIf="metricStates[param.parameter_name] as ms">
          <div *ngIf="ms.type === 'dynamic'" class="desc-field">
            <label>Trigger Description <span class="hint">— When does this scenario apply?</span></label>
            <textarea
              [(ngModel)]="ms.triggerDescription"
              placeholder="Describe the condition that makes this metric applicable (e.g. 'The customer asked about billing')…"
              rows="2"
              [class.filled]="ms.triggerDescription?.trim()">
            </textarea>
            <div class="char-count">{{ (ms.triggerDescription || '').length }} chars</div>
          </div>

          <div class="desc-field">
            <label>Answer Description <span class="hint">— What should the agent do?</span></label>
            <textarea
              [(ngModel)]="ms.answerDescription"
              placeholder="Describe what the agent must say or do to pass this evaluation…"
              rows="2"
              [class.filled]="ms.answerDescription?.trim()">
            </textarea>
            <div class="char-count">{{ (ms.answerDescription || '').length }} chars</div>
          </div>
        </ng-container>
      </div>

      <div *ngIf="!loading && parameters.length" class="footer">
        <span class="fill-status" [class.all-filled]="allFilled">
          {{ allFilled ? '✓ All descriptions filled' : (filledCount + ' / ' + parameters.length + ' filled') }}
        </span>
        <button [disabled]="!allFilled || submitting" (click)="submit()">
          {{ submitting ? 'Starting…' : 'Continue' }} <span>→</span>
        </button>
      </div>
    </div>
  `,
  styles: [`
    .page { max-width: 720px; margin: 0 auto; padding: 44px 24px 80px; }
    .page-header { margin-bottom: 28px; }
    .page-header h1 { font-size: 1.5rem; font-weight: 700; color: #111827; margin-bottom: 6px; }
    .page-header p { font-size: 0.9rem; color: #6b7280; line-height: 1.6; }
    .loading-msg { color: #9ca3af; font-size: 0.9rem; margin-bottom: 16px; }
    .error-msg { color: #dc2626; font-size: 0.88rem; margin-bottom: 16px; }
    .param-card {
      background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
      padding: 20px 24px; margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .param-header {
      display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap;
    }
    .param-name {
      font-family: var(--mono); font-size: 0.88rem; font-weight: 600; color: #111827;
      background: #f3f4f6; padding: 3px 10px; border-radius: 4px; flex: 1;
    }
    .type-toggle { display: flex; gap: 0; border: 1px solid #e5e7eb; border-radius: 6px; overflow: hidden; }
    .toggle-btn {
      padding: 5px 14px; font-size: 0.78rem; font-weight: 600; border: none; cursor: pointer;
      background: #f9fafb; color: #6b7280; transition: all 0.15s;
    }
    .toggle-btn.active { background: var(--accent); color: #fff; }
    .na-badge {
      font-size: 0.7rem; font-weight: 600; background: #fef3c7; color: #92400e;
      padding: 2px 8px; border-radius: 999px;
    }
    .desc-field { margin-bottom: 14px; }
    .desc-field label { display: block; font-size: 0.82rem; font-weight: 600; color: #374151; margin-bottom: 6px; }
    .desc-field .hint { font-weight: 400; color: #9ca3af; }
    textarea {
      width: 100%; padding: 10px 12px; border: 1px solid #e5e7eb;
      border-radius: 8px; font-size: 0.9rem; font-family: var(--font);
      resize: vertical; background: #fafafa; color: #111827;
      line-height: 1.55; outline: none; transition: border-color 0.15s;
      box-sizing: border-box;
    }
    textarea:focus { border-color: var(--accent); }
    textarea.filled { border-color: #d1d5db; }
    .char-count { margin-top: 4px; text-align: right; font-size: 0.72rem; color: #9ca3af; }
    .footer { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
    .fill-status { font-size: 0.82rem; color: #9ca3af; }
    .fill-status.all-filled { color: #16a34a; }
    button {
      padding: 11px 28px; background: var(--accent); color: #fff; border: none;
      border-radius: 8px; font-size: 0.9rem; font-weight: 600; cursor: pointer;
      display: flex; align-items: center; gap: 7px; transition: all 0.2s;
    }
    button:disabled { background: #e5e7eb; color: #9ca3af; cursor: not-allowed; }
  `]
})
export class DescriptionsComponent implements OnInit {
  parameters: ParameterInfo[] = [];
  metricStates: Record<string, MetricState> = {};
  loading = true;
  submitting = false;
  error = '';
  private sessionId = '';

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private svc: SessionService,
  ) {}

  ngOnInit() {
    this.sessionId = this.route.snapshot.params['sessionId'];
    this.svc.getSession(this.sessionId).subscribe({
      next: s => {
        this.parameters = s.parameters ?? [];
        this.parameters.forEach(p => {
          this.metricStates[p.parameter_name] = {
            type: p.has_na ? 'dynamic' : 'static',
            answerDescription: '',
            triggerDescription: '',
          };
        });
        this.loading = false;
      },
      error: () => { this.error = 'Failed to load parameters'; this.loading = false; }
    });
  }

  setType(paramName: string, type: 'static' | 'dynamic') {
    if (this.metricStates[paramName]) {
      this.metricStates[paramName] = { ...this.metricStates[paramName], type };
    }
  }

  get allFilled(): boolean {
    return this.parameters.every(p => {
      const ms = this.metricStates[p.parameter_name];
      if (!ms) return false;
      const answerFilled = ms.answerDescription.trim().length > 0;
      const triggerFilled = ms.type === 'static' || ms.triggerDescription.trim().length > 0;
      return answerFilled && triggerFilled;
    });
  }

  get filledCount(): number {
    return this.parameters.filter(p => {
      const ms = this.metricStates[p.parameter_name];
      if (!ms) return false;
      const answerFilled = ms.answerDescription.trim().length > 0;
      const triggerFilled = ms.type === 'static' || ms.triggerDescription.trim().length > 0;
      return answerFilled && triggerFilled;
    }).length;
  }

  submit() {
    if (!this.allFilled) return;
    this.submitting = true;

    const descriptions: Record<string, MetricConfig> = {};
    this.parameters.forEach(p => {
      const ms = this.metricStates[p.parameter_name];
      if (ms.type === 'static') {
        descriptions[p.parameter_name] = {
          type: 'static',
          answer_description: ms.answerDescription.trim(),
        };
      } else {
        descriptions[p.parameter_name] = {
          type: 'dynamic',
          answer_description: ms.answerDescription.trim(),
          trigger_description: ms.triggerDescription.trim(),
        };
      }
    });

    this.svc.submitDescriptions(this.sessionId, descriptions).subscribe({
      next: () => this.router.navigate([`/progress/${this.sessionId}`]),
      error: e => { this.error = e.error?.detail || 'Submission failed'; this.submitting = false; }
    });
  }
}
