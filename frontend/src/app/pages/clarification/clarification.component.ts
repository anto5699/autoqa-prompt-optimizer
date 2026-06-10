import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { SessionService } from '../../core/services/session.service';
import { ClarifyingQuestion } from '../../core/models/session.model';

@Component({
  selector: 'app-clarification',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="page">
      <div class="page-header">
        <h1>Answer {{ questions.length }} Clarifying Questions</h1>
        <p>Before optimization begins, the AI identified semantic ambiguities in your descriptions that could cause misclassifications. Your answers will be injected into the evaluation prompts.</p>
      </div>

      <div class="progress-bar-row">
        <div class="progress-track">
          <div class="progress-fill" [style.width.%]="questions.length ? (answeredCount / questions.length * 100) : 0"></div>
        </div>
        <span class="progress-label" [class.all-done]="answeredCount === questions.length && questions.length > 0">
          {{ answeredCount }} / {{ questions.length }} answered
        </span>
      </div>

      <ng-container *ngFor="let group of groups">
        <div class="param-group">
          <div class="param-group-header">
            <code class="param-group-id">{{ group.paramName }}</code>
            <span class="badge" [class.answer]="group.ruleType==='answer'" [class.trigger]="group.ruleType==='trigger'">
              {{ group.ruleType }}
            </span>
          </div>
          <div *ngFor="let q of group.questions; let qi = index" class="question-card" [class.answered]="!!answers[q.question_id]?.trim()">
            <div class="question-top">
              <div class="q-number" [class.answered]="!!answers[q.question_id]?.trim()">
                {{ answers[q.question_id]?.trim() ? '✓' : (qi + 1) }}
              </div>
              <div>
                <p class="q-text">{{ q.question_text }}</p>
                <p class="q-rationale">Why this matters: {{ q.rationale }}</p>
              </div>
            </div>
            <textarea
              [(ngModel)]="answers[q.question_id]"
              [class.answered]="!!answers[q.question_id]?.trim()"
              rows="2"
              placeholder="Your answer…"
            ></textarea>
          </div>
        </div>
      </ng-container>

      <div *ngIf="error" class="error-msg">{{ error }}</div>
      <div class="footer">
        <button [disabled]="!allAnswered || loading" (click)="submit()">
          {{ loading ? 'Submitting…' : 'Start Optimization' }} <span style="font-size:1.1rem">→</span>
        </button>
      </div>
    </div>
  `,
  styleUrls: ['./clarification.component.css']
})
export class ClarificationComponent implements OnInit {
  questions: ClarifyingQuestion[] = [];
  answers: Record<string, string> = {};
  loading = false;
  error = '';
  private sessionId = '';

  constructor(private route: ActivatedRoute, private svc: SessionService, private router: Router) {}

  ngOnInit() {
    this.sessionId = this.route.snapshot.params['sessionId'];
    this.svc.getSession(this.sessionId).subscribe({
      next: s => {
        this.questions = s.clarifying_questions;
        this.questions.forEach(q => this.answers[q.question_id] = '');
      },
      error: () => this.error = 'Failed to load session'
    });
  }

  get groups(): { paramName: string; ruleType: string; questions: ClarifyingQuestion[] }[] {
    const map = new Map<string, ClarifyingQuestion[]>();
    for (const q of this.questions) {
      if (!map.has(q.parameter_name)) map.set(q.parameter_name, []);
      map.get(q.parameter_name)!.push(q);
    }
    return Array.from(map.entries()).map(([paramName, qs]) => ({
      paramName,
      ruleType: 'answer',
      questions: qs,
    }));
  }

  get answeredCount(): number {
    return this.questions.filter(q => this.answers[q.question_id]?.trim()).length;
  }

  get allAnswered(): boolean {
    return this.questions.every(q => this.answers[q.question_id]?.trim());
  }

  submit() {
    this.loading = true;
    this.svc.submitAnswers(this.sessionId, this.answers).subscribe({
      next: () => this.router.navigate([`/progress/${this.sessionId}`]),
      error: () => { this.error = 'Submission failed'; this.loading = false; }
    });
  }
}
