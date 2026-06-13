import { Component, OnInit, ViewEncapsulation } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { SessionService } from '../../core/services/session.service';
import { FinalReport, ParameterReport } from '../../core/models/report.model';

@Component({
  selector: 'app-print-report',
  standalone: true,
  imports: [CommonModule],
  encapsulation: ViewEncapsulation.None,
  template: `
    <div *ngIf="loading" class="print-loading">Generating PDF — please wait…</div>

    <div *ngIf="report" class="print-root">

      <!-- Cover -->
      <div class="print-cover">
        <div class="print-logo">AutoQA Prompt Optimizer</div>
        <h1 class="print-title">Optimization Report</h1>
        <table class="print-meta-table">
          <tr><td>Session</td><td><code>{{ report.session_id }}</code></td></tr>
          <tr><td>Generated</td><td>{{ report.generated_at | date:'medium' }}</td></tr>
          <tr><td>Accuracy target</td><td>{{ pct(report.summary.accuracy_target) }}</td></tr>
          <tr><td>Total conversations</td><td>{{ report.summary.total_conversations }}</td></tr>
          <tr><td>Total iterations</td><td>{{ report.summary.total_iterations }}</td></tr>
        </table>
      </div>

      <!-- Overall summary -->
      <div class="print-section">
        <h2 class="print-h2">Overall Performance Summary</h2>
        <div class="print-kpi-row">
          <div class="print-kpi">
            <div class="print-kpi-val" [style.color]="accColor(report.summary.overall_accuracy, report.summary.accuracy_target)">
              {{ pct(report.summary.overall_accuracy) }}
            </div>
            <div class="print-kpi-lbl">Overall Accuracy</div>
          </div>
          <div class="print-kpi">
            <div class="print-kpi-val">{{ pct(report.summary.overall_precision) }}</div>
            <div class="print-kpi-lbl">Overall Precision</div>
          </div>
          <div class="print-kpi">
            <div class="print-kpi-val">{{ pct(report.summary.overall_recall) }}</div>
            <div class="print-kpi-lbl">Overall Recall</div>
          </div>
          <div class="print-kpi">
            <div class="print-kpi-val" [style.color]="report.summary.parameters_meeting_target === report.summary.total_parameters ? '#16a34a' : '#d97706'">
              {{ report.summary.parameters_meeting_target }}/{{ report.summary.total_parameters }}
            </div>
            <div class="print-kpi-lbl">Parameters Met Target</div>
          </div>
        </div>
      </div>

      <!-- Description updates overview -->
      <div class="print-section">
        <h2 class="print-h2">Description Updates Overview</h2>
        <p class="print-p">Summary of prompt description changes made across all parameters to achieve accuracy improvements.</p>
        <table class="print-table">
          <thead>
            <tr>
              <th>Parameter</th><th>Initial Accuracy</th><th>Final Accuracy</th>
              <th>Delta</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let e of allEntries">
              <td><code>{{ e.key }}</code></td>
              <td>{{ e.val.initial_accuracy != null ? pct(e.val.initial_accuracy) : '—' }}</td>
              <td [style.color]="accColor(e.val.final_accuracy, report.summary.accuracy_target)">
                {{ pct(e.val.final_accuracy) }}
              </td>
              <td [style.color]="e.val.initial_accuracy != null ? deltaColor(e.val.final_accuracy - e.val.initial_accuracy) : '#6b7280'">
                {{ e.val.initial_accuracy != null ? deltaStr(e.val) : '—' }}
              </td>
              <td>{{ statusLabel(e.val.status) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Per-parameter section -->
      <div *ngFor="let e of allEntries" class="print-param-block">
        <div class="print-param-header">
          <code class="print-param-id">{{ e.key }}</code>
          <span class="print-badge" [class]="e.val.status">{{ statusLabel(e.val.status) }}</span>
        </div>

        <div class="print-metrics-row">
          <div class="print-metric"><div class="pm-lbl">Accuracy</div><div class="pm-val" [style.color]="accColor(e.val.final_accuracy, report.summary.accuracy_target)">{{ pct(e.val.final_accuracy) }}</div></div>
          <div class="print-metric"><div class="pm-lbl">Precision</div><div class="pm-val">{{ pct(e.val.final_precision) }}</div></div>
          <div class="print-metric"><div class="pm-lbl">Recall</div><div class="pm-val">{{ pct(e.val.final_recall) }}</div></div>
          <div class="print-metric"><div class="pm-lbl">F1</div><div class="pm-val">{{ pct(e.val.final_f1) }}</div></div>
          <div class="print-metric"><div class="pm-lbl">N/A Count</div><div class="pm-val">{{ e.val.not_applicable_count }}</div></div>
        </div>

        <div class="print-matrix-wrap">
          <div class="pm-title">Confusion Matrix</div>
          <div class="print-matrix">
            <div class="matrix-cell cell-tp"><div class="m-val">{{ e.val.confusion_matrix.tp }}</div><div class="m-lbl">True Pos</div></div>
            <div class="matrix-cell cell-fp"><div class="m-val">{{ e.val.confusion_matrix.fp }}</div><div class="m-lbl">False Pos</div></div>
            <div class="matrix-cell cell-fn"><div class="m-val">{{ e.val.confusion_matrix.fn }}</div><div class="m-lbl">False Neg</div></div>
            <div class="matrix-cell cell-tn"><div class="m-val">{{ e.val.confusion_matrix.tn }}</div><div class="m-lbl">True Neg</div></div>
          </div>
        </div>

        <div *ngIf="e.val.iteration_history.length > 1" class="print-chart-wrap">
          <div class="pm-title">Accuracy Improvement Trend</div>
          <svg width="400" height="80" style="display:block;overflow:visible">
            <line [attr.x1]="8" [attr.y1]="trendTargetY(80, report.summary.accuracy_target)"
                  [attr.x2]="392" [attr.y2]="trendTargetY(80, report.summary.accuracy_target)"
                  stroke="#e5e7eb" stroke-width="1" stroke-dasharray="4,3"/>
            <text [attr.x]="396" [attr.y]="trendTargetY(80, report.summary.accuracy_target) + 4"
                  font-size="9" fill="#9ca3af" font-family="monospace">target</text>
            <polyline [attr.points]="trendPoints(e.val.iteration_history, 400, 80)"
                      fill="none" stroke="#4f46e5" stroke-width="2" stroke-linejoin="round"/>
            <circle *ngFor="let pt of trendDots(e.val.iteration_history, 400, 80, report.summary.accuracy_target)"
                    [attr.cx]="pt.x" [attr.cy]="pt.y" r="4"
                    [attr.fill]="pt.met ? '#16a34a' : '#4f46e5'"/>
          </svg>
          <div class="trend-labels">
            <span *ngFor="let h of e.val.iteration_history" class="trend-lbl">i{{ h.iteration }}</span>
          </div>
        </div>

        <div class="pm-title" style="margin-top:12px">Description Updates</div>
        <div class="print-prompt-grid">
          <div>
            <div class="prompt-col-lbl">Before ({{ e.val.initial_accuracy != null ? pct(e.val.initial_accuracy) : '—' }})</div>
            <pre class="print-prompt-pre">{{ e.val.initial_prompt }}</pre>
          </div>
          <div>
            <div class="prompt-col-lbl after-lbl">After ({{ pct(e.val.final_accuracy) }})</div>
            <pre class="print-prompt-pre after">{{ e.val.final_prompt }}</pre>
          </div>
        </div>

        <div *ngIf="e.val.status === 'max_iterations_reached'" class="print-rca-block">
          <div class="print-rca-title">Root Cause Analysis — Why This Parameter Did Not Converge</div>
          <p *ngIf="e.val.rca_findings" class="print-rca-text">{{ e.val.rca_findings }}</p>
          <p *ngIf="!e.val.rca_findings" class="print-rca-text print-rca-na">No RCA data available for this parameter.</p>
          <div *ngIf="e.val.recommendations?.length" class="print-recs">
            <div class="print-recs-title">Recommendations to Improve Accuracy</div>
            <ul><li *ngFor="let r of e.val.recommendations">{{ r }}</li></ul>
          </div>
          <div *ngIf="!e.val.recommendations?.length" class="print-recs">
            <div class="print-recs-title">General Recommendations</div>
            <ul>
              <li>Review the description for ambiguous language that cannot be determined from transcript text alone.</li>
              <li>Examine false positives and false negatives to understand where the model misclassifies.</li>
              <li>Tighten PASS_CRITERIA with explicit examples if false positives dominate; broaden if false negatives dominate.</li>
              <li>Verify that ground truth labels are consistent across annotators.</li>
            </ul>
          </div>
        </div>

        <div *ngIf="e.val.regression_warning" class="print-regression">
          <strong>Regression Warning:</strong> {{ e.val.regression_warning.message }}
        </div>
      </div>

    </div>
  `,
  styles: [`
    body { font-family: system-ui, sans-serif; margin: 0; background: #fff; color: #111827; }
    code { font-family: monospace; font-size: 0.85em; }
    .print-loading { padding: 2rem; text-align: center; font-size: 1rem; color: #6b7280; }
    .print-root { max-width: 900px; margin: 0 auto; padding: 2rem; }
    .print-cover { text-align: center; padding: 3rem 0 2rem; border-bottom: 2px solid #e5e7eb; margin-bottom: 2rem; }
    .print-logo  { font-size: 0.85rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #4f46e5; margin-bottom: 1rem; }
    .print-title { font-size: 2rem; font-weight: 700; margin: 0 0 1.5rem; }
    .print-meta-table { margin: 0 auto; border-collapse: collapse; font-size: 0.9rem; }
    .print-meta-table td { padding: 4px 16px; }
    .print-meta-table td:first-child { font-weight: 600; color: #6b7280; text-align: right; }
    .print-section { margin-bottom: 2rem; page-break-inside: avoid; }
    .print-h2 { font-size: 1.2rem; font-weight: 700; border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; margin: 0 0 1rem; }
    .print-p  { font-size: 0.9rem; color: #374151; margin: 0 0 1rem; }
    .print-kpi-row { display: flex; gap: 1rem; }
    .print-kpi { flex: 1; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; text-align: center; }
    .print-kpi-val { font-size: 1.6rem; font-weight: 700; }
    .print-kpi-lbl { font-size: 0.78rem; color: #6b7280; margin-top: 4px; }
    .print-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
    .print-table th { background: #f3f4f6; padding: 8px 10px; text-align: left; font-weight: 600; border-bottom: 1px solid #d1d5db; }
    .print-table td { padding: 7px 10px; border-bottom: 1px solid #f3f4f6; }
    .print-param-block { page-break-before: always; padding: 0 0 1.5rem; border-bottom: 2px solid #e5e7eb; margin-bottom: 1.5rem; }
    .print-param-header { display: flex; align-items: center; gap: 12px; margin-bottom: 1rem; }
    .print-param-id { font-size: 1.05rem; font-weight: 700; }
    .print-badge { font-size: 0.75rem; padding: 3px 10px; border-radius: 12px; font-weight: 600; }
    .print-badge.converged { background: #dcfce7; color: #15803d; }
    .print-badge.max_iterations_reached { background: #fef3c7; color: #92400e; }
    .print-metrics-row { display: flex; gap: 8px; margin-bottom: 1rem; }
    .print-metric { flex: 1; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px; text-align: center; }
    .pm-lbl { font-size: 0.72rem; color: #6b7280; }
    .pm-val { font-size: 1.1rem; font-weight: 700; }
    .pm-title { font-size: 0.82rem; font-weight: 600; color: #374151; margin-bottom: 6px; }
    .print-matrix-wrap { margin-bottom: 1rem; }
    .print-matrix { display: grid; grid-template-columns: 1fr 1fr; width: 160px; gap: 2px; }
    .matrix-cell { padding: 8px; text-align: center; border-radius: 4px; }
    .cell-tp { background: #dcfce7; }
    .cell-tn { background: #dbeafe; }
    .cell-fp { background: #fee2e2; }
    .cell-fn { background: #fef9c3; }
    .m-val { font-size: 1.1rem; font-weight: 700; }
    .m-lbl { font-size: 0.7rem; color: #6b7280; }
    .print-chart-wrap { margin-bottom: 1rem; }
    .trend-labels { display: flex; justify-content: space-between; margin-top: 2px; max-width: 400px; }
    .trend-lbl { font-size: 0.65rem; color: #9ca3af; font-family: monospace; }
    .print-prompt-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 1rem; }
    .prompt-col-lbl { font-size: 0.78rem; font-weight: 600; color: #6b7280; margin-bottom: 4px; }
    .after-lbl { color: #16a34a; }
    .print-prompt-pre { margin: 0; padding: 10px 12px; font-size: 0.8rem; line-height: 1.55; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; white-space: pre-wrap; word-break: break-word; font-family: monospace; }
    .print-prompt-pre.after { background: #f0fdf4; border-color: #86efac; }
    .print-rca-block { background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; padding: 12px 16px; margin-bottom: 1rem; }
    .print-rca-title { font-size: 0.88rem; font-weight: 700; color: #9a3412; margin-bottom: 6px; }
    .print-rca-text  { font-size: 0.88rem; color: #431407; margin: 0 0 8px; line-height: 1.55; }
    .print-rca-na    { color: #9a3412; font-style: italic; }
    .print-recs-title { font-size: 0.82rem; font-weight: 600; color: #374151; margin: 8px 0 4px; }
    .print-recs ul   { margin: 0; padding-left: 1.2rem; font-size: 0.85rem; color: #374151; }
    .print-recs li   { margin-bottom: 3px; }
    .print-regression { font-size: 0.82rem; color: #991b1b; background: #fee2e2; border-radius: 6px; padding: 8px 12px; margin-top: 8px; }
    @media print {
      .print-loading { display: none; }
      .print-param-block { page-break-before: always; }
      .print-cover { page-break-after: always; }
      @page { margin: 1.5cm; }
    }
  `]
})
export class PrintReportComponent implements OnInit {
  report: FinalReport | null = null;
  loading = true;

  constructor(private route: ActivatedRoute, private svc: SessionService) {}

  ngOnInit() {
    const id = this.route.snapshot.params['sessionId'];
    this.svc.getReport(id).subscribe({
      next: (r: any) => {
        if (r?.status === 'in_progress') return;
        this.report = r;
        this.loading = false;
        setTimeout(() => window.print(), 600);
      },
      error: () => { this.loading = false; }
    });
  }

  get allEntries(): { key: string; val: ParameterReport }[] {
    if (!this.report) return [];
    return Object.entries(this.report.parameters)
      .sort((a, b) => {
        if (a[1].status === b[1].status) return b[1].final_accuracy - a[1].final_accuracy;
        return a[1].status === 'converged' ? -1 : 1;
      })
      .map(([key, val]) => ({ key, val }));
  }

  pct(v: number): string { return (v * 100).toFixed(1) + '%'; }
  accColor(v: number, target = 0.90): string { return v >= target ? '#16a34a' : v >= 0.75 ? '#d97706' : '#dc2626'; }
  deltaColor(d: number): string { return d >= 0 ? '#16a34a' : '#dc2626'; }
  deltaStr(p: ParameterReport): string {
    if (p.initial_accuracy == null) return '';
    const d = p.final_accuracy - p.initial_accuracy;
    return (d >= 0 ? '+' : '') + (d * 100).toFixed(1) + 'pp';
  }
  statusLabel(s: string): string {
    const m: Record<string, string> = { converged: 'Converged', max_iterations_reached: 'Max iterations', pending: 'Pending', optimizing: 'Optimizing' };
    return m[s] ?? s;
  }
  trendTargetY(height: number, target: number): number { const pad = 8; return pad + (height - pad * 2) * (1 - target); }
  trendPoints(history: { accuracy: number }[], width: number, height: number): string {
    const pad = 8; const W = width - pad * 2, H = height - pad * 2;
    return history.map((e, i) => { const x = pad + (i / Math.max(history.length - 1, 1)) * W; const y = pad + H * (1 - e.accuracy); return `${x},${y}`; }).join(' ');
  }
  trendDots(history: { accuracy: number }[], width: number, height: number, target: number): { x: number; y: number; met: boolean }[] {
    const pad = 8; const W = width - pad * 2, H = height - pad * 2;
    return history.map((e, i) => ({ x: pad + (i / Math.max(history.length - 1, 1)) * W, y: pad + H * (1 - e.accuracy), met: e.accuracy >= target }));
  }
}
