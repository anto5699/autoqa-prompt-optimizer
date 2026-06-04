import { Component, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { Subscription, interval } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { SessionService } from '../../core/services/session.service';
import { SseService } from '../../core/services/sse.service';

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

const TERMINAL_PHASES = new Set(['complete', 'error']);

@Component({
  selector: 'app-progress',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="page">
      <h1>Optimization in Progress</h1>

      <div class="phase-row">
        <div class="phase-badge" [class.active]="isActive" [class.done]="phase === 'complete'" [class.err]="phase === 'error'">
          <span class="pulse-dot" *ngIf="isActive"></span>
          {{ phaseLabel }}
        </div>
        <span class="iteration-tag" *ngIf="iteration > 0">Iteration {{ iteration }}</span>
      </div>

      <div class="log-box" #logBox>
        <div *ngFor="let msg of log" class="log-line">{{ msg }}</div>
        <div *ngIf="!log.length" class="log-line muted">Starting…</div>
        <div *ngIf="isActive" class="log-line working">
          <span class="blink">▋</span>&nbsp;Working…
        </div>
      </div>

      <div class="params" *ngIf="params.length">
        <h2>Rule Accuracy</h2>
        <div *ngFor="let p of params" class="param-row">
          <span class="rule-id">{{ p.rule_id }}</span>
          <span class="badge" [class]="statusClass(p.accuracy)">{{ (p.accuracy * 100).toFixed(1) }}%</span>
          <span class="status-text">{{ p.status }}</span>
        </div>
      </div>

      <div *ngIf="error" class="error">{{ error }}</div>
    </div>
  `,
  styleUrls: ['./progress.component.css']
})
export class ProgressComponent implements OnInit, OnDestroy, AfterViewChecked {
  phase = 'ingesting';
  log: string[] = [];
  params: { rule_id: string; accuracy: number; status: string }[] = [];
  iteration = 0;
  error = '';
  private subs = new Subscription();
  private sessionId = '';
  private shouldScroll = false;

  @ViewChild('logBox') private logBox!: ElementRef<HTMLElement>;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private svc: SessionService,
    private sse: SseService,
  ) {}

  get phaseLabel(): string {
    return PHASE_LABELS[this.phase] ?? this.phase.replace(/_/g, ' ');
  }

  get isActive(): boolean {
    return !TERMINAL_PHASES.has(this.phase);
  }

  ngOnInit() {
    this.sessionId = this.route.snapshot.params['sessionId'];

    this.subs.add(
      this.sse.connect(this.sessionId).subscribe({
        next: evt => {
          if (evt.type === 'progress') {
            this.phase = evt.data['phase'] as string;
            if (evt.data['message']) {
              this.log.push(evt.data['message'] as string);
              this.shouldScroll = true;
            }
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
          if (s.current_phase === 'awaiting_clarification' && s.clarifying_questions?.length) {
            this.router.navigate([`/clarification/${this.sessionId}`]);
            return;
          }
          this.phase = s.current_phase;
          this.iteration = s.current_iteration;
          this.params = Object.entries(s.parameter_summary).map(([rule_id, v]) => ({
            rule_id, accuracy: v.accuracy, status: v.status
          }));
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

  ngOnDestroy() { this.subs.unsubscribe(); }

  statusClass(acc: number) { return acc >= 0.8 ? 'green' : acc >= 0.7 ? 'amber' : 'red'; }
}
