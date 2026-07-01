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
    <div *ngIf="loading" class="print-loading">Generating report — please wait…</div>

    <div *ngIf="report" class="print-root">

      <!-- Cover -->
      <div class="print-cover">
        <div class="print-logo">AutoQA Prompt Optimizer</div>
        <h1 class="print-title">Optimization Report</h1>
        <div class="cover-kpi-grid">
          <div class="cover-kpi" [style.border-color]="accColor(report.summary.overall_accuracy, report.summary.accuracy_target)">
            <div class="cover-kpi-val" [style.color]="accColor(report.summary.overall_accuracy, report.summary.accuracy_target)">{{ pct(report.summary.overall_accuracy) }}</div>
            <div class="cover-kpi-lbl">Final Accuracy</div>
          </div>
          <div class="cover-kpi">
            <div class="cover-kpi-val">{{ report.summary.parameters_meeting_target }}/{{ report.summary.total_parameters }}</div>
            <div class="cover-kpi-lbl">Parameters Met Target</div>
          </div>
          <div class="cover-kpi">
            <div class="cover-kpi-val">{{ report.summary.total_iterations }}</div>
            <div class="cover-kpi-lbl">Iterations</div>
          </div>
          <div class="cover-kpi">
            <div class="cover-kpi-val">{{ report.summary.total_conversations }}</div>
            <div class="cover-kpi-lbl">Conversations</div>
          </div>
        </div>
        <table class="print-meta-table">
          <tr><td>Session</td><td><code>{{ report.session_id }}</code></td></tr>
          <tr><td>Generated</td><td>{{ report.generated_at | date:'medium' }}</td></tr>
          <tr><td>Accuracy target</td><td>{{ pct(report.summary.accuracy_target) }}</td></tr>
          <tr *ngIf="report.summary.models_used?.evaluator">
            <td>Evaluation model</td><td>{{ report.summary.models_used?.evaluator }}</td>
          </tr>
          <tr *ngIf="report.summary.models_used?.optimizer">
            <td>Reasoning model</td><td>{{ report.summary.models_used?.optimizer }}</td>
          </tr>
        </table>
      </div>

      <!-- Overall Performance Summary -->
      <div class="print-section">
        <h2 class="print-h2">Overall Performance Summary</h2>

        <!-- Before → After banner -->
        <div *ngIf="avgInitialAccuracy !== null" class="delta-banner">
          <div class="delta-item">
            <div class="delta-val" [style.color]="accColor(avgInitialAccuracy ?? 0, report.summary.accuracy_target)">{{ pct(avgInitialAccuracy ?? 0) }}</div>
            <div class="delta-lbl">Avg accuracy before optimization</div>
          </div>
          <div class="delta-arrow">→</div>
          <div class="delta-item">
            <div class="delta-val" [style.color]="accColor(report.summary.overall_accuracy, report.summary.accuracy_target)">{{ pct(report.summary.overall_accuracy) }}</div>
            <div class="delta-lbl">Avg accuracy after optimization</div>
          </div>
          <div class="delta-gain">
            <div class="delta-gain-val" [style.color]="deltaColor(report.summary.overall_accuracy - (avgInitialAccuracy ?? 0))">
              {{ report.summary.overall_accuracy - (avgInitialAccuracy ?? 0) >= 0 ? '+' : '' }}{{ ((report.summary.overall_accuracy - (avgInitialAccuracy ?? 0)) * 100).toFixed(1) }}pp
            </div>
            <div class="delta-lbl">overall improvement</div>
          </div>
        </div>

        <!-- Precision / Recall / F1 KPIs -->
        <div class="print-kpi-row">
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
            <div class="print-kpi-lbl">Parameters Met Target ({{ pct(report.summary.accuracy_target) }})</div>
          </div>
        </div>
      </div>

      <!-- Parameter-level results table -->
      <div class="print-section">
        <h2 class="print-h2">Parameter-Level Results</h2>
        <table class="print-table">
          <thead>
            <tr>
              <th>Parameter</th>
              <th>Version</th>
              <th>Initial Accuracy</th>
              <th>Final Accuracy</th>
              <th>Improvement</th>
              <th>Precision</th>
              <th>Recall</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let e of allEntries">
              <td><code>{{ e.key }}</code></td>
              <td>{{ e.val.version?.toUpperCase() || 'V1' }}</td>
              <td>{{ e.val.initial_accuracy != null ? pct(e.val.initial_accuracy) : '—' }}</td>
              <td [style.color]="accColor(e.val.final_accuracy, report.summary.accuracy_target)">{{ pct(e.val.final_accuracy) }}</td>
              <td [style.color]="e.val.initial_accuracy != null ? deltaColor(e.val.final_accuracy - e.val.initial_accuracy) : '#6b7280'">
                {{ e.val.initial_accuracy != null ? deltaStr(e.val) : '—' }}
              </td>
              <td>{{ pct(e.val.final_precision) }}</td>
              <td>{{ pct(e.val.final_recall) }}</td>
              <td><span class="tbl-badge" [class]="e.val.status">{{ statusLabel(e.val.status) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Per-parameter detail sections -->
      <div *ngFor="let e of allEntries" class="print-param-block">

        <!-- Header -->
        <div class="print-param-header">
          <div class="param-header-left">
            <code class="print-param-id">{{ e.key }}</code>
            <span class="print-badge" [class]="e.val.status">{{ statusLabel(e.val.status) }}</span>
          </div>
          <div class="param-header-acc" *ngIf="e.val.initial_accuracy != null">
            <span class="ha-before" [style.color]="accColor(e.val.initial_accuracy, report.summary.accuracy_target)">{{ pct(e.val.initial_accuracy) }}</span>
            <span class="ha-arrow">→</span>
            <span class="ha-after" [style.color]="accColor(e.val.final_accuracy, report.summary.accuracy_target)">{{ pct(e.val.final_accuracy) }}</span>
            <span class="ha-delta" [style.color]="deltaColor(e.val.final_accuracy - e.val.initial_accuracy)">({{ deltaStr(e.val) }})</span>
          </div>
        </div>

        <!-- Metrics + Confusion matrix -->
        <div class="param-body-cols">
          <div class="param-metrics-col">
            <div class="pm-title">Final Metrics</div>
            <div class="print-metrics-row">
              <div class="print-metric">
                <div class="pm-lbl">Accuracy</div>
                <div class="pm-val" [style.color]="accColor(e.val.final_accuracy, report.summary.accuracy_target)">{{ pct(e.val.final_accuracy) }}</div>
              </div>
              <div class="print-metric">
                <div class="pm-lbl">Precision</div>
                <div class="pm-val">{{ pct(e.val.final_precision) }}</div>
              </div>
              <div class="print-metric">
                <div class="pm-lbl">Recall</div>
                <div class="pm-val">{{ pct(e.val.final_recall) }}</div>
              </div>
              <div class="print-metric">
                <div class="pm-lbl">F1</div>
                <div class="pm-val">{{ pct(e.val.final_f1) }}</div>
              </div>
              <div class="print-metric">
                <div class="pm-lbl">N/A Count</div>
                <div class="pm-val">{{ e.val.not_applicable_count }}</div>
              </div>
            </div>
          </div>
          <div class="param-matrix-col">
            <div class="pm-title">Confusion Matrix</div>
            <div class="print-matrix">
              <div class="matrix-cell cell-tp"><div class="m-val">{{ e.val.confusion_matrix.tp }}</div><div class="m-lbl">True Pos</div></div>
              <div class="matrix-cell cell-fp"><div class="m-val">{{ e.val.confusion_matrix.fp }}</div><div class="m-lbl">False Pos</div></div>
              <div class="matrix-cell cell-fn"><div class="m-val">{{ e.val.confusion_matrix.fn }}</div><div class="m-lbl">False Neg</div></div>
              <div class="matrix-cell cell-tn"><div class="m-val">{{ e.val.confusion_matrix.tn }}</div><div class="m-lbl">True Neg</div></div>
            </div>
          </div>
        </div>

        <!-- Accuracy improvement trend -->
        <div *ngIf="e.val.iteration_history.length > 1" class="print-chart-wrap">
          <div class="pm-title">Accuracy Improvement Trend</div>
          <svg width="500" height="80" style="display:block;overflow:visible">
            <line [attr.x1]="8" [attr.y1]="trendTargetY(80, report.summary.accuracy_target)"
                  [attr.x2]="492" [attr.y2]="trendTargetY(80, report.summary.accuracy_target)"
                  stroke="#e5e7eb" stroke-width="1" stroke-dasharray="4,3"/>
            <text [attr.x]="496" [attr.y]="trendTargetY(80, report.summary.accuracy_target) + 4"
                  font-size="9" fill="#9ca3af" font-family="monospace">target</text>
            <polyline [attr.points]="trendPoints(e.val.iteration_history, 500, 80)"
                      fill="none" stroke="#4f46e5" stroke-width="2" stroke-linejoin="round"/>
            <circle *ngFor="let pt of trendDots(e.val.iteration_history, 500, 80, report.summary.accuracy_target)"
                    [attr.cx]="pt.x" [attr.cy]="pt.y" r="4"
                    [attr.fill]="pt.met ? '#16a34a' : '#4f46e5'"/>
          </svg>
          <div class="trend-labels">
            <span *ngFor="let h of e.val.iteration_history" class="trend-lbl">iter {{ h.iteration }} — {{ pct(h.accuracy) }}</span>
          </div>
        </div>

        <!-- What changed (optimization notes) -->
        <div *ngIf="e.val.optimization_notes" class="opt-notes-box">
          <div class="opt-notes-title">What changed</div>
          <p class="opt-notes-text">{{ e.val.optimization_notes }}</p>
        </div>

        <!-- Prompt comparison -->
        <div class="pm-title prompt-section-title">Prompt Progression</div>
        <div class="prompt-three-grid">
          <div class="prompt-col">
            <div class="prompt-col-header">Original User Description</div>
            <pre class="prompt-box original">{{ e.val.original_description || '(none — AI generated baseline)' }}</pre>
          </div>
          <div class="prompt-col">
            <div class="prompt-col-header">
              Baseline Prompt
              <span *ngIf="e.val.initial_accuracy != null" class="acc-badge neutral">{{ pct(e.val.initial_accuracy!) }}</span>
            </div>
            <pre class="prompt-box baseline">{{ e.val.initial_prompt }}</pre>
          </div>
          <div class="prompt-col">
            <div class="prompt-col-header">
              Final Optimised Prompt
              <span class="acc-badge" [class.good]="e.val.final_accuracy >= report!.summary.accuracy_target" [class.bad]="e.val.final_accuracy < report!.summary.accuracy_target">{{ pct(e.val.final_accuracy) }}</span>
              <button class="prompt-copy-btn no-print" (click)="copyPrompt(e.key, e.val.final_prompt)">
                {{ copiedPdf[e.key] ? '✓ Copied' : 'Copy' }}
              </button>
            </div>
            <pre class="prompt-box final">{{ e.val.final_prompt }}</pre>
          </div>
        </div>

        <!-- Report Summary -->
        <div *ngIf="e.val.report_summary" class="print-report-summary"
             [class.print-summary-converged]="e.val.status === 'converged'"
             [class.print-summary-not-met]="e.val.status !== 'converged'">
          <div class="print-summary-title">
            {{ e.val.status === 'converged' ? 'How This Parameter Was Improved' : 'Why This Parameter Did Not Meet the Target' }}
          </div>
          <pre class="print-summary-text">{{ e.val.report_summary }}</pre>
        </div>

        <!-- Regression warning -->
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
    .print-root { max-width: 940px; margin: 0 auto; padding: 2rem; }

    /* Cover */
    .print-cover { text-align: center; padding: 3rem 0 2rem; border-bottom: 2px solid #e5e7eb; margin-bottom: 2rem; }
    .print-logo  { font-size: 0.8rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #4f46e5; margin-bottom: 1rem; }
    .print-title { font-size: 2rem; font-weight: 700; margin: 0 0 1.5rem; }
    .cover-kpi-grid { display: flex; justify-content: center; gap: 1rem; margin-bottom: 1.5rem; }
    .cover-kpi { background: #f9fafb; border: 2px solid #e5e7eb; border-radius: 10px; padding: 1rem 1.5rem; min-width: 120px; text-align: center; }
    .cover-kpi-val { font-size: 1.8rem; font-weight: 700; color: #111827; }
    .cover-kpi-lbl { font-size: 0.72rem; color: #6b7280; margin-top: 4px; }
    .print-meta-table { margin: 0 auto; border-collapse: collapse; font-size: 0.88rem; }
    .print-meta-table td { padding: 4px 16px; }
    .print-meta-table td:first-child { font-weight: 600; color: #6b7280; text-align: right; }

    /* Sections */
    .print-section { margin-bottom: 2rem; page-break-inside: avoid; }
    .print-h2 { font-size: 1.15rem; font-weight: 700; border-bottom: 2px solid #4f46e5; padding-bottom: 6px; margin: 0 0 1rem; color: #111827; }

    /* Before → After banner */
    .delta-banner { display: flex; align-items: center; justify-content: center; gap: 1.5rem; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 10px; padding: 1.2rem 2rem; margin-bottom: 1.2rem; }
    .delta-item { text-align: center; }
    .delta-val { font-size: 1.6rem; font-weight: 700; }
    .delta-lbl { font-size: 0.72rem; color: #6b7280; margin-top: 2px; }
    .delta-arrow { font-size: 1.8rem; color: #9ca3af; }
    .delta-gain { text-align: center; background: #fff; border-radius: 8px; padding: 8px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
    .delta-gain-val { font-size: 1.4rem; font-weight: 700; }

    /* KPI row */
    .print-kpi-row { display: flex; gap: 1rem; }
    .print-kpi { flex: 1; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; text-align: center; }
    .print-kpi-val { font-size: 1.5rem; font-weight: 700; }
    .print-kpi-lbl { font-size: 0.75rem; color: #6b7280; margin-top: 4px; }

    /* Overview table */
    .print-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    .print-table th { background: #f3f4f6; padding: 8px 10px; text-align: left; font-weight: 600; border-bottom: 2px solid #d1d5db; }
    .print-table td { padding: 7px 10px; border-bottom: 1px solid #f3f4f6; }
    .tbl-badge { font-size: 0.72rem; padding: 2px 8px; border-radius: 10px; font-weight: 600; white-space: nowrap; }
    .tbl-badge.converged { background: #dcfce7; color: #15803d; }
    .tbl-badge.max_iterations_reached { background: #fef3c7; color: #92400e; }

    /* Per-parameter block */
    .print-param-block { page-break-before: always; padding-bottom: 1.5rem; border-bottom: 2px solid #e5e7eb; margin-bottom: 1.5rem; }
    .print-param-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; flex-wrap: wrap; gap: 8px; }
    .param-header-left { display: flex; align-items: center; gap: 10px; }
    .print-param-id { font-size: 1.05rem; font-weight: 700; }
    .print-badge { font-size: 0.72rem; padding: 3px 10px; border-radius: 12px; font-weight: 600; }
    .print-badge.converged { background: #dcfce7; color: #15803d; }
    .print-badge.max_iterations_reached { background: #fef3c7; color: #92400e; }
    .param-header-acc { display: flex; align-items: center; gap: 6px; font-size: 0.95rem; }
    .ha-before { color: #6b7280; }
    .ha-arrow { color: #9ca3af; }
    .ha-after { font-weight: 700; font-size: 1.05rem; }
    .ha-delta { font-size: 0.85rem; }

    /* Metrics + matrix two-column */
    .param-body-cols { display: flex; gap: 1.5rem; margin-bottom: 1rem; align-items: flex-start; }
    .param-metrics-col { flex: 1; }
    .param-matrix-col { flex-shrink: 0; }
    .print-metrics-row { display: flex; gap: 6px; flex-wrap: wrap; }
    .print-metric { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px 10px; text-align: center; min-width: 72px; }
    .pm-lbl { font-size: 0.68rem; color: #6b7280; }
    .pm-val { font-size: 1.05rem; font-weight: 700; margin-top: 2px; }
    .pm-title { font-size: 0.78rem; font-weight: 600; color: #374151; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em; }

    /* Confusion matrix */
    .print-matrix { display: grid; grid-template-columns: 1fr 1fr; width: 148px; gap: 3px; }
    .matrix-cell { padding: 10px 8px; text-align: center; border-radius: 4px; }
    .cell-tp { background: #dcfce7; }
    .cell-tn { background: #dbeafe; }
    .cell-fp { background: #fee2e2; }
    .cell-fn { background: #fef9c3; }
    .m-val { font-size: 1.2rem; font-weight: 700; }
    .m-lbl { font-size: 0.65rem; color: #6b7280; margin-top: 2px; }

    /* Trend chart */
    .print-chart-wrap { margin-bottom: 1rem; }
    .trend-labels { display: flex; justify-content: space-between; margin-top: 4px; max-width: 500px; }
    .trend-lbl { font-size: 0.63rem; color: #9ca3af; font-family: monospace; }

    /* What changed box */
    .opt-notes-box { background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 12px 16px; margin-bottom: 1rem; }
    .opt-notes-title { font-size: 0.78rem; font-weight: 700; color: #15803d; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }
    .opt-notes-text { font-size: 0.88rem; color: #14532d; margin: 0; line-height: 1.6; }

    /* Prompt comparison */
    .prompt-section-title { margin-top: 12px; margin-bottom: 10px; }
    .prompt-three-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 16px; }
    .prompt-col { display: flex; flex-direction: column; }
    .prompt-col-header { font-size: 9px; font-weight: 700; text-transform: uppercase; color: #6b7280; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }
    .prompt-box { font-family: 'Courier New', monospace; font-size: 8px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; padding: 8px; border-radius: 4px; margin: 0; }
    .prompt-box.original { background: #f3f4f6; border: 1px solid #d1d5db; }
    .prompt-box.baseline { background: #eff6ff; border: 1px solid #bfdbfe; }
    .prompt-box.final    { background: #f0fdf4; border: 1px solid #a7f3d0; }
    .acc-badge { padding: 1px 5px; border-radius: 3px; font-size: 8px; font-weight: 600; }
    .acc-badge.neutral { background: #f3f4f6; color: #6b7280; }
    .acc-badge.good { background: #d1fae5; color: #065f46; }
    .acc-badge.bad  { background: #fee2e2; color: #991b1b; }
    .prompt-copy-btn { font-size: 0.72rem; padding: 3px 10px; border: 1px solid #16a34a; border-radius: 6px; background: #fff; color: #16a34a; cursor: pointer; font-weight: 600; flex-shrink: 0; }
    .prompt-copy-btn:hover { background: #f0fdf4; }

    /* Report Summary */
    .print-report-summary { border-radius: 8px; padding: 12px 16px; margin-bottom: 1rem; }
    .print-summary-converged { background: #f0fdf4; border: 1px solid #86efac; }
    .print-summary-not-met   { background: #fff7ed; border: 1px solid #fed7aa; }
    .print-summary-title { font-size: 0.82rem; font-weight: 700; margin-bottom: 6px; }
    .print-summary-converged .print-summary-title { color: #15803d; }
    .print-summary-not-met   .print-summary-title { color: #9a3412; }
    .print-summary-text { font-family: inherit; font-size: 0.85rem; color: inherit; line-height: 1.6; white-space: pre-wrap; word-break: break-word; margin: 0; }
    .print-summary-converged .print-summary-text { color: #14532d; }
    .print-summary-not-met   .print-summary-text { color: #431407; }

    /* Regression warning */
    .print-regression { font-size: 0.82rem; color: #991b1b; background: #fee2e2; border-radius: 6px; padding: 8px 12px; margin-top: 8px; }

    @media print {
      .print-loading { display: none; }
      .no-print { display: none !important; }
      .print-param-block { page-break-before: always; }
      .print-cover { page-break-after: always; }
      .print-section:nth-of-type(2) { page-break-after: always; }
      @page { margin: 1.5cm; }
    }
  `]
})
export class PrintReportComponent implements OnInit {
  report: FinalReport | null = null;
  loading = true;
  copiedPdf: Record<string, boolean> = {};

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

  get avgInitialAccuracy(): number | null {
    if (!this.report) return null;
    const vals = Object.values(this.report.parameters)
      .map(p => p.initial_accuracy)
      .filter((v): v is number => v != null);
    if (!vals.length) return null;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  }

  copyPrompt(key: string, text: string) {
    navigator.clipboard.writeText(text).catch(() => {});
    this.copiedPdf[key] = true;
    setTimeout(() => this.copiedPdf[key] = false, 2000);
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
