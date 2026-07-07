import { Component, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { Subscription, interval } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { SessionService } from '../../core/services/session.service';
import { SseService } from '../../core/services/sse.service';
import { ClarifyingQuestion, NodeProgress } from '../../core/models/session.model';

const PHASE_LABELS: Record<string, string> = {
  ingesting: 'Ingesting CSV',
  detecting_ambiguity: 'Detecting Ambiguity',
  awaiting_clarification: 'Awaiting Clarification',
  generating_baselines: 'Generating Baselines',
  evaluating: 'Evaluating Conversations',
  benchmarking: 'Benchmarking',
  analyzing_failures: 'Analysing Failures',
  optimizing_prompts: 'Optimising Descriptions',
  complete: 'Complete',
  error: 'Error',
};

const PHASE_LEVEL: Record<string, number> = {
  ingesting: 0, detecting_ambiguity: 1, awaiting_clarification: 2,
  generating_baselines: 3, evaluating: 4, benchmarking: 5,
  analyzing_failures: 6, optimizing_prompts: 7, complete: 8,
};

const PIPELINE = [
  { key: 'ingesting',          label: 'CSV Ingestion',       loop: false },
  { key: 'detecting_ambiguity',label: 'Ambiguity Detection', loop: false },
  { key: 'generating_baselines',label: 'Baseline Generation',loop: false },
  { key: 'evaluating',         label: 'Evaluator',           loop: true  },
  { key: 'benchmarking',       label: 'Benchmarking',        loop: true  },
  { key: 'analyzing_failures', label: 'RCA Analysis',        loop: true  },
  { key: 'optimizing_prompts', label: 'Prompt Optimizer',    loop: true  },
  { key: 'complete',           label: 'Finalize',            loop: false },
];

@Component({
  selector: 'app-progress',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="page">
      <div class="page-header">
        <h1>Optimization Running</h1>
        <p>The agent is iteratively evaluating conversations and refining your evaluation prompts.</p>
      </div>

      <div class="layout">
        <!-- Pipeline sidebar -->
        <div class="pipeline-card">
          <div class="pipeline-title">Agent Pipeline</div>
          <ng-container *ngFor="let node of pipeline; let idx = index">
            <div class="pipeline-node">
              <div class="node-dot-wrap">
                <div class="node-dot" [class.done]="isNodeDone(node.key)" [class.active]="phase === node.key">
                  <ng-container *ngIf="isNodeDone(node.key)">✓</ng-container>
                  <div *ngIf="phase === node.key && !isNodeDone(node.key)" class="node-dot-inner"></div>
                  <ng-container *ngIf="!isNodeDone(node.key) && phase !== node.key">○</ng-container>
                </div>
                <div *ngIf="phase === node.key" class="node-ring"></div>
              </div>
              <div class="node-info">
                <div class="node-label" [class.done]="isNodeDone(node.key)" [class.active]="phase === node.key">
                  {{ node.label }}
                </div>
                <div *ngIf="node.loop && phase === node.key && iteration > 0" class="node-iter">
                  Iteration {{ iteration }}
                </div>
              </div>
              <span *ngIf="node.loop" class="node-loop">↺</span>
            </div>
            <div *ngIf="idx < pipeline.length - 1" class="node-connector" [class.done]="isNodeDone(node.key)"></div>
          </ng-container>
        </div>

        <!-- Activity panel -->
        <div class="activity">
          <div style="display:flex;align-items:center;gap:10px;">
            <span class="phase-pill" [class.complete]="phase==='complete'" [class.error-pill]="phase==='error'">
              <span *ngIf="isActive" class="pulse-dot"></span>
              {{ phaseLabel }}
            </span>
            <span *ngIf="iteration > 0" class="iter-tag">Iteration {{ iteration }}</span>
          </div>

          <div *ngIf="phase === 'awaiting_clarification' && clarifyingQuestions.length" class="clarification-card">
            <div class="clarification-header">
              <div class="clarification-icon">?</div>
              <div>
                <div class="clarification-title">Clarification Needed</div>
                <div class="clarification-sub">The optimizer is stuck on the following parameters. Your answers will help it continue.</div>
              </div>
            </div>
            <div *ngFor="let q of clarifyingQuestions; trackBy: trackByQuestion" class="clarification-question">
              <div class="q-param">
                {{ cleanParamName(q.parameter_name) }}
                <span *ngIf="ruleTypeBadge(q.parameter_name)" class="q-rule-type">{{ ruleTypeBadge(q.parameter_name) }}</span>
              </div>
              <div class="q-text">{{ q.question_text }}</div>
              <ng-container *ngIf="q.question_type === 'pivot'; else freeText">
                <div class="pivot-options">
                  <label class="pivot-option">
                    <input type="radio" [name]="'pivot-' + q.question_id"
                           value="Yes" (change)="setAnswerStr(q.question_id, 'Yes')"> Yes, replace the logic
                  </label>
                  <label class="pivot-option">
                    <input type="radio" [name]="'pivot-' + q.question_id"
                           value="No" (change)="setAnswerStr(q.question_id, 'No')"> No, keep refining
                  </label>
                </div>
              </ng-container>
              <ng-template #freeText>
                <textarea class="q-input" rows="3" placeholder="Your answer…"
                  [value]="pendingAnswers[q.question_id] || ''"
                  (input)="setAnswer(q.question_id, $event)"></textarea>
              </ng-template>
            </div>
            <button class="btn-clarify" [disabled]="!allAnswered()" (click)="submitClarification()">
              Submit &amp; Continue
            </button>
          </div>

          <div *ngIf="phase === 'error'" class="error-card">
            <div class="error-card-header">
              <span class="error-card-icon">✕</span>
              <span class="error-card-title">Optimization failed</span>
            </div>
            <p class="error-card-body">{{ error || 'An unexpected error occurred. Check your API key and model configuration, then try again.' }}</p>
            <div class="error-actions">
              <button *ngIf="hasResumableData" class="btn-resume" (click)="resumeOptimization()" [disabled]="resuming">
                ↺ {{ resuming ? 'Resuming…' : 'Resume (5 more iterations)' }}
              </button>
              <button class="btn-start-over" (click)="startOver()">← Start Over</button>
            </div>
          </div>

          <div *ngIf="nodeProgress && nodeProgress.total > 1" class="node-progress-card">
            <div class="node-progress-row">
              <span class="node-progress-label">{{ nodeProgress.step }} / {{ nodeProgress.total }} processed</span>
              <span class="node-progress-pct">{{ nodeProgressPct }}%</span>
            </div>
            <div class="node-progress-track">
              <div class="node-progress-fill" [style.width.%]="nodeProgressPct"></div>
            </div>
          </div>

          <div class="log-box" #logBox>
            <span *ngIf="!log.length && phase !== 'error'" class="log-empty">Initialising…</span>
            <div *ngFor="let msg of log" class="log-line"
                 [class.ok]="msg.includes('✓') || msg.includes('converged')"
                 [class.err]="msg.includes('✗') || msg.includes('ERROR') || msg.includes('WARNING')">
              <span class="log-prompt">›</span>{{ msg }}
            </div>
            <span *ngIf="isActive" class="log-cursor">▋</span>
          </div>

          <div *ngIf="params.length" class="acc-card">
            <div class="acc-title">Parameter Accuracy</div>
            <div style="display:flex;flex-direction:column;gap:10px;">
              <div *ngFor="let p of params" class="acc-row">
                <code class="acc-rule-id">{{ p.rule_id }}</code>
                <div class="acc-track">
                  <div class="acc-fill" [style.width.%]="p.accuracy * 100" [style.background]="accColor(p.accuracy)"></div>
                </div>
                <span class="acc-val" [style.color]="accColor(p.accuracy)">{{ (p.accuracy * 100).toFixed(1) }}%</span>
                <span class="acc-check">{{ p.accuracy >= 0.90 ? '✓' : '' }}</span>
              </div>
            </div>
          </div>

          <div *ngIf="rcaParams.length" class="rca-panel">
            <div class="rca-panel-title">Why These Parameters Are Struggling</div>
            <div *ngFor="let p of rcaParams" class="rca-item">
              <div class="rca-item-header">
                <code class="acc-rule-id">{{ cleanParamName(p.rule_id) }}</code>
                <span *ngIf="ruleTypeBadge(p.rule_id)" class="q-rule-type">{{ ruleTypeBadge(p.rule_id) }}</span>
                <span class="rca-accuracy-badge" [style.color]="accColor(p.accuracy)">{{ (p.accuracy * 100).toFixed(1) }}%</span>
              </div>
              <pre class="rca-text">{{ p.rca_findings }}</pre>
            </div>
          </div>

          <div *ngIf="auditParams.length" class="audit-panel">
            <div class="audit-panel-title">Ground Truth Alignment Audit</div>
            <div *ngFor="let p of auditParams" class="audit-item">
              <div class="audit-item-header">
                <code class="acc-rule-id">{{ cleanParamName(p.rule_id) }}</code>
                <span *ngIf="ruleTypeBadge(p.rule_id)" class="q-rule-type">{{ ruleTypeBadge(p.rule_id) }}</span>
                <span class="audit-iteration-badge">Iteration {{ p.audit_iteration }}</span>
              </div>
              <pre class="audit-text">{{ p.alignment_audit }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  styleUrls: ['./progress.component.css']
})
export class ProgressComponent implements OnInit, OnDestroy, AfterViewChecked {
  phase = 'ingesting';
  log: string[] = [];
  params: { rule_id: string; accuracy: number; status: string; rca_findings?: string; alignment_audit?: string; audit_iteration?: number }[] = [];
  iteration = 0;
  error = '';
  resuming = false;
  nodeProgress: NodeProgress | null = null;
  pipeline = PIPELINE;
  clarifyingQuestions: ClarifyingQuestion[] = [];
  pendingAnswers: Record<string, string> = {};
  private maxLevel = 0;
  private subs = new Subscription();
  private sessionId = '';
  private shouldScroll = false;
  private awaitingResume = false;

  @ViewChild('logBox') private logBox!: ElementRef<HTMLElement>;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private svc: SessionService,
    private sse: SseService,
  ) {}

  get phaseLabel(): string { return PHASE_LABELS[this.phase] ?? this.phase.replace(/_/g, ' '); }
  get isActive(): boolean  { return !['complete', 'error'].includes(this.phase); }

  get nodeProgressPct(): number {
    if (!this.nodeProgress || this.nodeProgress.total === 0) return 0;
    return Math.round((this.nodeProgress.step / this.nodeProgress.total) * 100);
  }

  isNodeDone(key: string): boolean {
    const nodeLv = PHASE_LEVEL[key] ?? 0;
    const curLv  = PHASE_LEVEL[this.phase] ?? 0;
    return nodeLv < curLv;
  }

  accColor(acc: number): string {
    return acc >= 0.90 ? '#16a34a' : acc >= 0.75 ? '#d97706' : '#dc2626';
  }

  get rcaParams(): { rule_id: string; accuracy: number; status: string; rca_findings: string }[] {
    return this.params.filter(
      p => p.rca_findings && p.status !== 'converged'
    ) as { rule_id: string; accuracy: number; status: string; rca_findings: string }[];
  }

  get auditParams(): { rule_id: string; accuracy: number; status: string; alignment_audit: string; audit_iteration: number }[] {
    return this.params.filter(p => p.alignment_audit) as { rule_id: string; accuracy: number; status: string; alignment_audit: string; audit_iteration: number }[];
  }

  ngOnInit() {
    this.sessionId = this.route.snapshot.params['sessionId'];

    this.subs.add(
      this.sse.connect(this.sessionId).subscribe({
        next: evt => {
          if (evt.type === 'progress') {
            if (this.phase !== 'awaiting_clarification') {
              this.phase = evt.data['phase'] as string;
            }
            if (evt.data['message']) { this.log.push(evt.data['message'] as string); this.shouldScroll = true; }
            const np = evt.data['node_progress'] as NodeProgress | null;
            if (np) this.nodeProgress = np;
          }
          if (evt.type === 'complete') this.router.navigate([`/results/${this.sessionId}`]);
          if (evt.type === 'error') this.error = evt.data['message'] as string;
        },
        error: () => this.error = 'Stream connection failed'
      })
    );

    this.subs.add(
      interval(3000).pipe(switchMap(() => this.svc.getSession(this.sessionId))).subscribe({
        next: s => {
          this.phase = s.current_phase;
          this.iteration = s.current_iteration;
          this.params = Object.entries(s.parameter_summary).map(([rule_id, v]) => ({
            rule_id, accuracy: v.accuracy, status: v.status, rca_findings: v.rca_findings,
            alignment_audit: v.alignment_audit, audit_iteration: v.audit_iteration,
          }));
          this.nodeProgress = s.node_progress ?? null;
          if (s.current_phase === 'awaiting_clarification' && !this.awaitingResume) {
            if (!this.clarifyingQuestions.length) {
              this.clarifyingQuestions = s.clarifying_questions ?? [];
            }
          } else if (s.current_phase !== 'awaiting_clarification') {
            this.awaitingResume = false;
            this.clarifyingQuestions = [];
          }
          if (s.current_phase === 'error' && s.error_message) {
            this.error = s.error_message;
          }
          if (s.current_phase === 'complete') this.router.navigate([`/results/${this.sessionId}`]);
        }
      })
    );
  }

  ngAfterViewChecked() {
    if (this.shouldScroll && this.logBox) {
      const el = this.logBox.nativeElement;
      el.scrollTop = el.scrollHeight;
      this.shouldScroll = false;
    }
  }

  setAnswer(questionId: string, event: Event) {
    this.pendingAnswers[questionId] = (event.target as HTMLTextAreaElement).value;
  }

  setAnswerStr(questionId: string, value: string) {
    this.pendingAnswers[questionId] = value;
  }

  allAnswered(): boolean {
    return this.clarifyingQuestions.length > 0 &&
      this.clarifyingQuestions.every(q => (this.pendingAnswers[q.question_id] || '').trim().length > 0);
  }

  submitClarification() {
    const answers: Record<string, string> = {};
    for (const q of this.clarifyingQuestions) {
      answers[q.question_id] = (this.pendingAnswers[q.question_id] || '').trim();
    }
    this.awaitingResume = true;
    this.clarifyingQuestions = [];
    this.pendingAnswers = {};
    this.svc.submitAnswers(this.sessionId, answers).subscribe();
  }

  cleanParamName(name: string): string {
    return name.replace(/__answer$/, '').replace(/__trigger$/, '');
  }

  ruleTypeBadge(name: string): string {
    if (name.endsWith('__answer')) return 'Answer Rule';
    if (name.endsWith('__trigger')) return 'Trigger Rule';
    return '';
  }

  trackByQuestion = (_: number, q: ClarifyingQuestion) => q.question_id;

  get hasResumableData(): boolean {
    return this.params.some(p => p.accuracy > 0);
  }

  resumeOptimization(): void {
    this.resuming = true;
    this.svc.continueOptimization(this.sessionId, 5).subscribe({
      next: res => this.router.navigate(['/progress', res.new_session_id]),
      error: () => { this.resuming = false; },
    });
  }

  startOver() { this.router.navigate(['/upload']); }

  ngOnDestroy() { this.subs.unsubscribe(); }
}
