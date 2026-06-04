import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { SessionService } from '../../core/services/session.service';
import { RuleInfo } from '../../core/models/session.model';

@Component({
  selector: 'app-descriptions',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="page">
      <h1>AutoQA Prompt Optimizer</h1>
      <div class="card">
        <h2>Define Parameter Descriptions</h2>
        <p class="subtitle">
          Provide an initial description for each parameter. These will be iteratively
          refined to maximise evaluation accuracy.
        </p>

        <div *ngIf="loading" class="log-line muted">Loading parameters…</div>
        <div *ngIf="error" class="error">{{ error }}</div>

        <div *ngFor="let rule of rules" class="param-block">
          <div class="param-header">
            <span class="param-id">{{ rule.rule_id }}</span>
            <span class="badge" [class]="rule.rule_type">{{ rule.rule_type }}</span>
            <span class="meta">{{ rule.speaker }} · {{ rule.evaluation_type }}</span>
          </div>
          <textarea
            [(ngModel)]="descriptions[rule.rule_id]"
            placeholder="Describe what this parameter evaluates…"
            rows="3"
          ></textarea>
        </div>

        <div *ngIf="!loading && rules.length" class="actions">
          <button [disabled]="!allFilled || submitting" (click)="submit()">
            {{ submitting ? 'Starting…' : 'Start Optimization' }}
          </button>
          <span *ngIf="!allFilled" class="hint">All descriptions required</span>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .page { max-width: 880px; margin: 80px auto; padding: 0 24px; }
    h1 { font-size: 2rem; font-weight: 700; margin-bottom: 32px; color: var(--text); }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 40px; }
    h2 { font-size: 1.35rem; font-weight: 700; margin-bottom: 8px; }
    .subtitle { color: var(--text-muted); margin-bottom: 32px; font-size: 1rem; line-height: 1.5; }
    .param-block { margin-bottom: 28px; padding-bottom: 28px; border-bottom: 1px solid var(--border); }
    .param-block:last-of-type { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
    .param-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
    .param-id { font-weight: 600; font-size: 1rem; }
    .meta { font-size: 0.875rem; color: var(--text-muted); margin-left: auto; }
    .badge { font-size: 0.8rem; padding: 3px 10px; border-radius: 999px; font-weight: 600; text-transform: uppercase; }
    .badge.trigger { background: #e0e7ff; color: #4338ca; }
    .badge.answer { background: #dcfce7; color: #15803d; }
    textarea { width: 100%; padding: 11px 14px; border: 1px solid var(--border); border-radius: 8px; font-size: 1rem; font-family: inherit; resize: vertical; background: var(--bg); color: var(--text); line-height: 1.5; }
    textarea:focus { outline: none; border-color: var(--accent); }
    .actions { display: flex; align-items: center; gap: 16px; margin-top: 32px; }
    button { flex: 1; padding: 15px; background: var(--accent); color: #fff; border: none; border-radius: 8px; font-size: 1.05rem; font-weight: 600; cursor: pointer; transition: opacity .15s; }
    button:hover:not(:disabled) { opacity: 0.9; }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .hint { font-size: 0.95rem; color: var(--text-muted); }
    .error { color: var(--red, #ef4444); margin-bottom: 16px; font-size: 0.95rem; }
    .muted { color: var(--text-muted); font-size: 0.95rem; }
  `]
})
export class DescriptionsComponent implements OnInit {
  rules: RuleInfo[] = [];
  descriptions: Record<string, string> = {};
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
        this.rules = s.rules ?? [];
        this.rules.forEach(r => this.descriptions[r.rule_id] = '');
        this.loading = false;
      },
      error: () => { this.error = 'Failed to load parameters'; this.loading = false; }
    });
  }

  get allFilled(): boolean {
    return this.rules.every(r => this.descriptions[r.rule_id]?.trim().length > 0);
  }

  submit() {
    if (!this.allFilled) return;
    this.submitting = true;
    this.svc.submitDescriptions(this.sessionId, this.descriptions).subscribe({
      next: () => this.router.navigate([`/progress/${this.sessionId}`]),
      error: e => { this.error = e.error?.detail || 'Submission failed'; this.submitting = false; }
    });
  }
}
