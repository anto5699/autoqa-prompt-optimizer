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
      <h1>Clarify Evaluation Rules</h1>
      <div class="card" *ngFor="let q of questions; let i = index">
        <div class="rule-tag">{{ q.parameter_name }}</div>
        <p class="question">{{ q.question_text }}</p>
        <p class="rationale">{{ q.rationale }}</p>
        <textarea [(ngModel)]="answers[q.question_id]" placeholder="Your answer…" rows="3"></textarea>
      </div>
      <div *ngIf="error" class="error">{{ error }}</div>
      <button [disabled]="!allAnswered || loading" (click)="submit()">
        {{ loading ? 'Submitting…' : 'Submit & Continue' }}
      </button>
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
