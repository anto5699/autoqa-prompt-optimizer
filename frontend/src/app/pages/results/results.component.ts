import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute, Router } from '@angular/router';
import { SessionService } from '../../core/services/session.service';
import { FinalReport, ParameterReport } from '../../core/models/report.model';

type FilterKey = 'all' | 'converged' | 'not-met';

@Component({
  selector: 'app-results',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="page" *ngIf="report">
      <!-- Header -->
      <div class="page-header">
        <div>
          <h1>Optimization Complete</h1>
          <p>Session <code>{{ report.session_id }}</code> · {{ report.generated_at | date:'medium' }}</p>
        </div>
        <div class="header-btns">
          <button class="export-btn" [class.exported]="exported" (click)="exportCsv()">
            {{ exported ? '✓ Exported' : '↓ Export Evaluations CSV' }}
          </button>
          <button class="export-btn" [class.exported]="exportedPrompts" (click)="exportPromptsCsv()">
            {{ exportedPrompts ? '✓ Exported' : '↓ Export Prompts CSV' }}
          </button>
          <button class="export-btn pdf-btn" (click)="exportPdf()">
            ↗ Export Report PDF
          </button>
          <button class="export-btn" (click)="downloadTrace()">
            ↓ Debug Trace (JSON)
          </button>
        </div>
      </div>

      <!-- Models used -->
      <div *ngIf="report.summary.models_used?.evaluator" class="models-row">
        <span class="models-label">Models:</span>
        <span class="model-chip eval-chip">Evaluation: {{ report.summary.models_used?.evaluator }}</span>
        <span class="model-chip opt-chip">Reasoning: {{ report.summary.models_used?.optimizer }}</span>
      </div>

      <!-- KPI cards -->
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-val" [style.color]="overallColor">{{ pct(report.summary.overall_accuracy) }}</div>
          <div class="kpi-label">Overall Accuracy</div>
          <div class="kpi-sub">Target: {{ pct(report.summary.accuracy_target) }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:#16a34a">{{ report.summary.parameters_meeting_target }}/{{ report.summary.total_parameters }}</div>
          <div class="kpi-label">Met Target</div>
          <div class="kpi-sub">{{ pct(report.summary.accuracy_target) }} threshold</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val">{{ report.summary.total_iterations }}</div>
          <div class="kpi-label">Iterations</div>
          <div class="kpi-sub">optimization loops</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val">{{ report.summary.total_conversations }}</div>
          <div class="kpi-label">Conversations</div>
          <div class="kpi-sub">evaluated per iteration</div>
        </div>
      </div>

      <!-- Filter bar -->
      <div class="filter-bar">
        <span class="filter-label">Show:</span>
        <button *ngFor="let f of filters" class="filter-btn" [class.active]="filter===f.key" (click)="filter=f.key">{{ f.label }}</button>
      </div>

      <div *ngIf="filteredEntries.length === 0" class="empty-msg">No parameters match this filter.</div>

      <!-- Parameter cards -->
      <div *ngFor="let entry of filteredEntries" class="param-card">
        <div class="param-row" (click)="toggle(entry.key)">
          <code class="param-id">{{ entry.key }}</code>
          <span class="status-badge" [class]="entry.val.status">{{ statusLabel(entry.val.status) }}</span>
          <div class="acc-journey">
            <ng-container *ngIf="entry.val.initial_accuracy != null">
              <span class="acc-val" [style.color]="accColor(entry.val.initial_accuracy, report.summary.accuracy_target)" style="font-size:0.85rem">
                {{ pct(entry.val.initial_accuracy) }}
              </span>
              <span class="acc-arrow">→</span>
            </ng-container>
            <span class="acc-val" [style.color]="accColor(entry.val.final_accuracy, report.summary.accuracy_target)" style="font-size:1rem">
              {{ pct(entry.val.final_accuracy) }}
            </span>
            <ng-container *ngIf="entry.val.initial_accuracy != null">
              <span class="acc-delta" [style.color]="deltaColor(entry.val.final_accuracy - entry.val.initial_accuracy)">
                {{ delta(entry.val) }}
              </span>
            </ng-container>
          </div>
          <svg *ngIf="entry.val.iteration_history.length > 1" [attr.width]="100" [attr.height]="28" style="flex-shrink:0;overflow:visible">
            <line [attr.x1]="6" [attr.y1]="targetY(28)" [attr.x2]="94" [attr.y2]="targetY(28)" stroke="#e5e7eb" stroke-width="1" stroke-dasharray="3,2"/>
            <polyline [attr.points]="sparkPoints(entry.val.iteration_history, 100, 28)" fill="none" stroke="#4f46e5" stroke-width="1.5" stroke-linejoin="round"/>
            <circle *ngFor="let pt of sparkDots(entry.val.iteration_history, 100, 28, report.summary.accuracy_target)"
                    [attr.cx]="pt.x" [attr.cy]="pt.y" r="2.5"
                    [attr.fill]="pt.met ? '#16a34a' : '#4f46e5'"/>
          </svg>
          <span class="chevron" [class.open]="expanded[entry.key]">▼</span>
        </div>

        <!-- Detail panel -->
        <div *ngIf="expanded[entry.key]" class="detail">
          <!-- Original / Baseline / Optimised prompts -->
          <div class="prompt-three-grid">
            <div class="prompt-col">
              <div class="prompt-col-header">
                <span class="prompt-col-label">Original User Description</span>
                <span class="prompt-acc-badge neutral">From CSV</span>
              </div>
              <pre class="prompt-box original">{{ entry.val.original_description || '(none — AI generated baseline from scratch)' }}</pre>
            </div>
            <div class="prompt-col">
              <div class="prompt-col-header">
                <span class="prompt-col-label">Baseline Prompt</span>
                <span *ngIf="entry.val.initial_accuracy !== null && entry.val.initial_accuracy !== undefined" class="prompt-acc-badge neutral">{{ (entry.val.initial_accuracy! * 100).toFixed(1) }}% accuracy</span>
              </div>
              <pre class="prompt-box baseline">{{ entry.val.initial_prompt }}</pre>
            </div>
            <div class="prompt-col">
              <div class="prompt-col-header">
                <span class="prompt-col-label">Final Optimised Prompt</span>
                <span class="prompt-acc-badge" [class.good]="entry.val.final_accuracy >= report!.summary.accuracy_target" [class.bad]="entry.val.final_accuracy < report!.summary.accuracy_target">{{ (entry.val.final_accuracy * 100).toFixed(1) }}% accuracy</span>
                <button class="copy-btn" (click)="copy(entry.key, entry.val.final_prompt)">Copy</button>
              </div>
              <pre class="prompt-box final">{{ entry.val.final_prompt }}</pre>
            </div>
          </div>

          <!-- Metrics + Confusion matrix + Sparkline -->
          <div class="metrics-row">
            <div>
              <div class="section-title">Final Metrics</div>
              <div class="metrics-grid">
                <div class="metric-box"><div class="metric-lbl">Precision</div><div class="metric-val">{{ pct(entry.val.final_precision) }}</div></div>
                <div class="metric-box"><div class="metric-lbl">Recall</div><div class="metric-val">{{ pct(entry.val.final_recall) }}</div></div>
                <div class="metric-box"><div class="metric-lbl">F1 Score</div><div class="metric-val">{{ pct(entry.val.final_f1) }}</div></div>
                <div class="metric-box"><div class="metric-lbl">N/A Count</div><div class="metric-val">{{ entry.val.not_applicable_count }}</div></div>
              </div>
            </div>
            <div>
              <div class="section-title">Confusion Matrix</div>
              <div class="matrix-grid">
                <div class="matrix-cell cell-tp"><div class="m-val">{{ entry.val.confusion_matrix.tp }}</div><div class="m-lbl">True Pos</div></div>
                <div class="matrix-cell cell-fp"><div class="m-val">{{ entry.val.confusion_matrix.fp }}</div><div class="m-lbl">False Pos</div></div>
                <div class="matrix-cell cell-fn"><div class="m-val">{{ entry.val.confusion_matrix.fn }}</div><div class="m-lbl">False Neg</div></div>
                <div class="matrix-cell cell-tn"><div class="m-val">{{ entry.val.confusion_matrix.tn }}</div><div class="m-lbl">True Neg</div></div>
              </div>
            </div>
            <div *ngIf="entry.val.iteration_history.length > 1">
              <div class="section-title">Accuracy Trajectory</div>
              <svg [attr.width]="240" [attr.height]="56" style="display:block;overflow:visible">
                <line [attr.x1]="6" [attr.y1]="targetY(56, report.summary.accuracy_target)" [attr.x2]="234" [attr.y2]="targetY(56, report.summary.accuracy_target)" stroke="#e5e7eb" stroke-width="1" stroke-dasharray="4,3"/>
                <text [attr.x]="238" [attr.y]="targetY(56, report.summary.accuracy_target) + 4" font-size="9" fill="#9ca3af" font-family="monospace">target</text>
                <polyline [attr.points]="sparkPoints(entry.val.iteration_history, 240, 56)" fill="none" stroke="#4f46e5" stroke-width="2" stroke-linejoin="round"/>
                <circle *ngFor="let pt of sparkDots(entry.val.iteration_history, 240, 56, report.summary.accuracy_target)"
                        [attr.cx]="pt.x" [attr.cy]="pt.y" r="3.5"
                        [attr.fill]="pt.met ? '#16a34a' : '#4f46e5'"/>
              </svg>
              <div style="display:flex;justify-content:space-between;margin-top:4px;">
                <span *ngFor="let h of entry.val.iteration_history" style="font-size:0.65rem;color:#9ca3af;font-family:var(--mono)">i{{ h.iteration }}</span>
              </div>
            </div>
          </div>

          <!-- Report Summary -->
          <div *ngIf="entry.val.report_summary" class="report-summary-box"
               [class.summary-converged]="entry.val.status === 'converged'"
               [class.summary-not-met]="entry.val.status !== 'converged'">
            <div class="report-summary-title">
              {{ entry.val.status === 'converged' ? 'How This Parameter Was Improved' : 'Why This Parameter Did Not Meet the Target' }}
            </div>
            <pre class="report-summary-text">{{ entry.val.report_summary }}</pre>
          </div>

          <!-- Optimization notes -->
          <p *ngIf="entry.val.optimization_notes" class="opt-notes">
            <strong>Changes made: </strong>{{ entry.val.optimization_notes }}
          </p>

          <!-- Conversation results -->
          <div *ngIf="entry.val.conversation_results?.length">
            <button class="convs-toggle" (click)="toggleConvs(entry.key)">
              <span class="convs-arrow" [class.open]="showConvs[entry.key]">▶</span>
              {{ showConvs[entry.key] ? 'Hide' : 'Show' }} conversation-level results ({{ entry.val.conversation_results.length }})
            </button>
            <div *ngIf="showConvs[entry.key]" class="conv-table-wrap">
              <table class="conv-table">
                <thead>
                  <tr>
                    <th>Conversation</th><th>Ground Truth</th><th>Prediction</th><th>Match</th>
                  </tr>
                </thead>
                <tbody>
                  <tr *ngFor="let c of entry.val.conversation_results" [class.mismatch]="c.correct === false">
                    <td class="conv-id">{{ c.conversation_id }}</td>
                    <td><span class="lbl-chip" [class]="c.ground_truth.toLowerCase()">{{ c.ground_truth }}</span></td>
                    <td><span class="lbl-chip" [class]="c.prediction.toLowerCase()">{{ c.prediction }}</span></td>
                    <td style="text-align:center">
                      <span *ngIf="c.correct === true" class="match-ok">✓</span>
                      <span *ngIf="c.correct === false" class="match-fail">✗</span>
                      <span *ngIf="c.correct === null" class="match-na">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
      <!-- Continue Optimization panel — shown when unconverged params exist -->
      <div *ngIf="unconvergedParams.length > 0" class="continue-panel">
        <h3 class="continue-title">Continue Optimization</h3>
        <p class="continue-desc">
          {{ unconvergedParams.length }} parameter(s) did not reach the accuracy target of
          {{ pct(report!.summary.accuracy_target) }}. You can run additional optimization
          rounds carrying all context and iteration history forward into a new session.
        </p>
        <div class="continue-chips">
          <code *ngFor="let p of unconvergedParams" class="param-chip-sm">{{ p }}</code>
        </div>
        <div class="continue-controls">
          <label class="iter-label">
            Additional iterations
            <input class="iter-input" type="number" [(ngModel)]="additionalIterations" min="1" max="10">
          </label>
          <button class="continue-btn" [disabled]="continuing" (click)="startContinuation()">
            {{ continuing ? 'Starting…' : 'Continue Optimization' }}
          </button>
        </div>
      </div>
    </div>

    <div *ngIf="!report && !error" class="loading-msg">Loading results…</div>
    <div *ngIf="error" class="error-msg">{{ error }}</div>
  `,
  styleUrls: ['./results.component.css']
})
export class ResultsComponent implements OnInit {
  report: FinalReport | null = null;
  expanded: Record<string, boolean> = {};
  showConvs: Record<string, boolean> = {};
  copied: Record<string, boolean> = {};
  exported = false;
  exportedPrompts = false;
  filter: FilterKey = 'all';
  error = '';
  additionalIterations = 5;
  continuing = false;
  private sessionId = '';

  filters = [
    { key: 'all' as FilterKey,       label: 'All parameters' },
    { key: 'converged' as FilterKey, label: 'Converged'       },
    { key: 'not-met' as FilterKey,   label: 'Not met'         },
  ];

  constructor(private route: ActivatedRoute, private svc: SessionService, private router: Router, private http: HttpClient) {}

  ngOnInit() {
    this.sessionId = this.route.snapshot.params['sessionId'];
    this.svc.getReport(this.sessionId).subscribe({
      next: (r: any) => {
        if (r?.status === 'in_progress') {
          this.error = `Optimization still in progress (phase: ${r.current_phase}). Return to the progress page.`;
          return;
        }
        this.report = r;
      },
      error: () => this.error = 'Failed to load report'
    });
  }

  get filteredEntries(): { key: string; val: ParameterReport }[] {
    if (!this.report) return [];
    return Object.entries(this.report.parameters)
      .filter(([, v]) => {
        if (this.filter === 'converged') return v.status === 'converged';
        if (this.filter === 'not-met')   return v.status !== 'converged';
        return true;
      })
      .sort((a, b) => {
        if (a[1].status === b[1].status) return b[1].final_accuracy - a[1].final_accuracy;
        return a[1].status === 'converged' ? -1 : 1;
      })
      .map(([key, val]) => ({ key, val }));
  }

  get overallColor(): string {
    if (!this.report) return '#111827';
    return this.report.summary.overall_accuracy >= this.report.summary.accuracy_target ? '#16a34a' : '#d97706';
  }

  toggle(key: string)      { this.expanded[key] = !this.expanded[key]; }
  toggleConvs(key: string) { this.showConvs[key] = !this.showConvs[key]; }

  pct(v: number): string { return (v * 100).toFixed(1) + '%'; }

  accColor(v: number, target = 0.90): string {
    return v >= target ? '#16a34a' : v >= 0.75 ? '#d97706' : '#dc2626';
  }

  delta(p: ParameterReport): string {
    if (p.initial_accuracy == null) return '';
    const d = p.final_accuracy - p.initial_accuracy;
    return (d >= 0 ? '+' : '') + (d * 100).toFixed(1) + 'pp';
  }

  deltaColor(d: number): string { return d >= 0 ? '#16a34a' : '#dc2626'; }

  statusLabel(s: string): string {
    const m: Record<string, string> = {
      converged: 'Converged', max_iterations_reached: 'Max iterations',
      pending: 'Pending', optimizing: 'Optimizing',
    };
    return m[s] ?? s;
  }

  targetY(height: number, target = 0.90): number {
    const pad = 6;
    return pad + (height - pad * 2) * (1 - target);
  }

  sparkPoints(history: { accuracy: number }[], width: number, height: number): string {
    const pad = 6;
    const W = width - pad * 2, H = height - pad * 2;
    return history.map((e, i) => {
      const x = pad + (i / Math.max(history.length - 1, 1)) * W;
      const y = pad + H * (1 - e.accuracy);
      return `${x},${y}`;
    }).join(' ');
  }

  sparkDots(history: { accuracy: number }[], width: number, height: number, target: number): { x: number; y: number; met: boolean }[] {
    const pad = 6;
    const W = width - pad * 2, H = height - pad * 2;
    return history.map((e, i) => ({
      x: pad + (i / Math.max(history.length - 1, 1)) * W,
      y: pad + H * (1 - e.accuracy),
      met: e.accuracy >= target,
    }));
  }

  copy(key: string, text: string) {
    navigator.clipboard.writeText(text).catch(() => {});
    this.copied[key] = true;
    setTimeout(() => this.copied[key] = false, 2000);
  }

  exportCsv() {
    if (!this.report) return;

    // Wide format: one row per conversation, one column-group per rule
    const ruleIds = Object.keys(this.report.parameters).sort();

    // Collect conversation IDs in stable order from the first rule that has results
    const convIds: string[] = [];
    const seen = new Set<string>();
    for (const ruleId of ruleIds) {
      for (const c of this.report.parameters[ruleId].conversation_results ?? []) {
        if (!seen.has(c.conversation_id)) {
          seen.add(c.conversation_id);
          convIds.push(c.conversation_id);
        }
      }
    }

    // Build lookup: ruleId → conversationId → result
    const lookup: Record<string, Record<string, { ground_truth: string; prediction: string; correct: boolean | null }>> = {};
    for (const ruleId of ruleIds) {
      lookup[ruleId] = {};
      for (const c of this.report.parameters[ruleId].conversation_results ?? []) {
        lookup[ruleId][c.conversation_id] = c;
      }
    }

    const headers = ['conversation_id'];
    for (const ruleId of ruleIds) {
      headers.push(`${ruleId}_ground_truth`, `${ruleId}_prediction`, `${ruleId}_correct`);
    }

    const rows = [headers.join(',')];
    for (const convId of convIds) {
      const row: string[] = [convId];
      for (const ruleId of ruleIds) {
        const c = lookup[ruleId]?.[convId];
        if (c) {
          const correct = c.correct === null ? 'NA' : c.correct ? 'true' : 'false';
          row.push(c.ground_truth, c.prediction, correct);
        } else {
          row.push('', '', '');
        }
      }
      rows.push(row.join(','));
    }

    const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `optimization-results-${this.report.session_id.slice(0, 8)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    this.exported = true;
    setTimeout(() => this.exported = false, 2500);
  }

  get unconvergedParams(): string[] {
    if (!this.report) return [];
    return Object.entries(this.report.parameters)
      .filter(([, v]) => v.status === 'max_iterations_reached')
      .map(([k]) => k);
  }

  startContinuation() {
    if (!this.sessionId || this.continuing) return;
    const iters = Math.min(10, Math.max(1, this.additionalIterations));
    this.continuing = true;
    this.svc.continueOptimization(this.sessionId, iters).subscribe({
      next: (resp) => {
        this.continuing = false;
        this.router.navigate(['/progress', resp.new_session_id]);
      },
      error: () => {
        this.continuing = false;
      },
    });
  }

  exportPromptsCsv() {
    if (!this.report) return;
    const rows = ['parameter_name,rule_type,optimised_prompt'];
    for (const [ruleId, param] of Object.entries(this.report.parameters)) {
      const ruleType = ruleId.includes('_trigger_') ? 'trigger' : 'answer';
      const safePrompt = (param.final_prompt ?? '').replace(/"/g, '""');
      rows.push(`${ruleId},${ruleType},"${safePrompt}"`);
    }
    const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `optimised-prompts-${this.report.session_id.slice(0, 8)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    this.exportedPrompts = true;
    setTimeout(() => this.exportedPrompts = false, 2500);
  }

  exportPdf() {
    window.open(`/results/${this.sessionId}/print`, '_blank');
  }

  downloadTrace() {
    this.http.get(`/api/sessions/${this.sessionId}/trace`).subscribe(data => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `autoqa-trace-${this.sessionId}.json`; a.click();
      URL.revokeObjectURL(url);
    });
  }
}
