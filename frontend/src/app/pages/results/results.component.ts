import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { SessionService } from '../../core/services/session.service';
import { FinalReport, ParameterReport } from '../../core/models/report.model';

@Component({
  selector: 'app-results',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="page" *ngIf="report">
      <div class="page-header">
        <h1>Optimization Results</h1>
        <button class="export-btn" (click)="exportCsv()">Export CSV</button>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><div class="val">{{ report.summary.total_parameters }}</div><div class="lbl">Parameters</div></div>
        <div class="summary-card"><div class="val green">{{ report.summary.parameters_meeting_target }}</div><div class="lbl">Met Target</div></div>
        <div class="summary-card"><div class="val" [class]="accClass(report.summary.overall_accuracy)">{{ pct(report.summary.overall_accuracy) }}</div><div class="lbl">Overall Accuracy</div></div>
        <div class="summary-card"><div class="val">{{ report.summary.total_iterations }}</div><div class="lbl">Iterations</div></div>
      </div>

      <div *ngFor="let entry of paramEntries" class="param-card">
        <div class="param-header" (click)="toggle(entry.key)">
          <span class="rule-id">{{ entry.key }}</span>
          <span class="badge" [class]="accClass(entry.val.final_accuracy)">{{ pct(entry.val.final_accuracy) }}</span>
          <span class="status-chip" [class]="entry.val.status">{{ entry.val.status }}</span>
          <span class="chevron">{{ expanded[entry.key] ? '▲' : '▼' }}</span>
        </div>
        <div class="param-detail" *ngIf="expanded[entry.key]">
          <div class="section compare-grid">
            <div class="compare-col">
              <div class="compare-header">
                <h3>Before</h3>
                <span class="badge" [class]="accClass(entry.val.initial_accuracy ?? 0)">{{ entry.val.initial_accuracy != null ? pct(entry.val.initial_accuracy) : '—' }}</span>
              </div>
              <pre>{{ entry.val.initial_prompt }}</pre>
            </div>
            <div class="compare-col">
              <div class="compare-header">
                <h3>After</h3>
                <span class="badge" [class]="accClass(entry.val.final_accuracy)">{{ pct(entry.val.final_accuracy) }}</span>
              </div>
              <pre>{{ entry.val.final_prompt }}</pre>
              <button class="copy-btn" (click)="copy(entry.val.final_prompt)">Copy</button>
            </div>
          </div>
          <div class="section metrics-grid">
            <div><div class="metric-lbl">Precision</div><div class="metric-val">{{ pct(entry.val.final_precision) }}</div></div>
            <div><div class="metric-lbl">Recall</div><div class="metric-val">{{ pct(entry.val.final_recall) }}</div></div>
            <div><div class="metric-lbl">F1</div><div class="metric-val">{{ pct(entry.val.final_f1) }}</div></div>
            <div><div class="metric-lbl">N/A count</div><div class="metric-val">{{ entry.val.not_applicable_count }}</div></div>
          </div>
          <div class="section">
            <h3>Confusion Matrix</h3>
            <div class="matrix">
              <div class="cell tp">TP<br>{{ entry.val.confusion_matrix.tp }}</div>
              <div class="cell fp">FP<br>{{ entry.val.confusion_matrix.fp }}</div>
              <div class="cell fn">FN<br>{{ entry.val.confusion_matrix.fn }}</div>
              <div class="cell tn">TN<br>{{ entry.val.confusion_matrix.tn }}</div>
            </div>
          </div>
          <div class="section" *ngIf="entry.val.iteration_history.length > 1">
            <h3>Accuracy Progress</h3>
            <svg width="100%" height="60" viewBox="0 0 400 60">
              <polyline [attr.points]="sparkline(entry.val)" fill="none" stroke="var(--accent)" stroke-width="2"/>
            </svg>
          </div>
          <div class="section" *ngIf="entry.val.rca_findings">
            <h3>Root Cause Analysis</h3>
            <p>{{ entry.val.rca_findings }}</p>
          </div>
          <div class="section" *ngIf="entry.val.recommendations.length">
            <h3>Recommendations</h3>
            <ul><li *ngFor="let r of entry.val.recommendations">{{ r }}</li></ul>
          </div>
          <div class="section" *ngIf="entry.val.conversation_results?.length">
            <h3>Conversation-Level Results</h3>
            <table class="conv-table">
              <thead>
                <tr>
                  <th>Conversation ID</th>
                  <th>Ground Truth</th>
                  <th>LLM Prediction</th>
                  <th>Match</th>
                </tr>
              </thead>
              <tbody>
                <tr *ngFor="let c of entry.val.conversation_results" [class.mismatch]="c.correct === false" [class.na-row]="c.correct === null">
                  <td class="conv-id">{{ c.conversation_id }}</td>
                  <td><span class="label-chip" [class]="c.ground_truth.toLowerCase()">{{ c.ground_truth }}</span></td>
                  <td><span class="label-chip" [class]="c.prediction.toLowerCase()">{{ c.prediction }}</span></td>
                  <td class="match-col">
                    <span *ngIf="c.correct === true" class="match-icon ok">✓</span>
                    <span *ngIf="c.correct === false" class="match-icon fail">✗</span>
                    <span *ngIf="c.correct === null" class="match-icon na">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
    <div *ngIf="!report && !error" class="loading">Loading results…</div>
    <div *ngIf="error" class="error">{{ error }}</div>
  `,
  styleUrls: ['./results.component.css']
})
export class ResultsComponent implements OnInit {
  report: FinalReport | null = null;
  expanded: Record<string, boolean> = {};
  error = '';

  constructor(private route: ActivatedRoute, private svc: SessionService) {}

  ngOnInit() {
    const id = this.route.snapshot.params['sessionId'];
    this.svc.getReport(id).subscribe({
      next: (r: any) => {
        if (r?.status === 'in_progress') {
          this.error = `Optimization is still in progress (phase: ${r.current_phase}). Please wait on the progress page.`;
          return;
        }
        this.report = r;
      },
      error: () => this.error = 'Failed to load report'
    });
  }

  get paramEntries(): { key: string; val: ParameterReport }[] {
    if (!this.report) return [];
    return Object.entries(this.report.parameters).map(([key, val]) => ({ key, val }));
  }

  toggle(key: string) { this.expanded[key] = !this.expanded[key]; }
  pct(v: number) { return (v * 100).toFixed(1) + '%'; }
  accClass(v: number) { return v >= 0.8 ? 'green' : v >= 0.7 ? 'amber' : 'red'; }

  sparkline(p: ParameterReport): string {
    const h = p.iteration_history;
    if (!h.length) return '';
    const W = 400, H = 60, pad = 4;
    const xs = h.map((_, i) => (i / Math.max(h.length - 1, 1)) * (W - pad * 2) + pad);
    const ys = h.map(e => H - pad - e.accuracy * (H - pad * 2));
    return h.map((_, i) => `${xs[i]},${ys[i]}`).join(' ');
  }

  copy(text: string) { navigator.clipboard.writeText(text); }

  exportCsv() {
    if (!this.report) return;
    const rows = ['rule_id,conversation_id,ground_truth,prediction,correct'];
    for (const [ruleId, param] of Object.entries(this.report.parameters)) {
      for (const c of param.conversation_results ?? []) {
        const correct = c.correct === null ? 'NA' : c.correct ? 'true' : 'false';
        rows.push(`${ruleId},${c.conversation_id},${c.ground_truth},${c.prediction},${correct}`);
      }
    }
    const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `optimization-results-${this.report.session_id.slice(0, 8)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
