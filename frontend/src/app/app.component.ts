import { Component, OnInit, OnDestroy } from '@angular/core';
import { RouterOutlet, Router, NavigationEnd } from '@angular/router';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { filter } from 'rxjs/operators';

const STEPS = [
  { id: 1, label: 'Upload' },
  { id: 2, label: 'Describe' },
  { id: 3, label: 'Clarify' },
  { id: 4, label: 'Optimize' },
  { id: 5, label: 'Report' },
];

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, CommonModule],
  template: `
    <div style="min-height:100vh;background:#f4f5f7;">
      <div class="topbar">
        <div class="topbar-logo-row">
          <div class="topbar-logo">
            <div class="logo-icon">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="5.5" stroke="white" stroke-width="1.4"/>
                <path d="M4.5 7.5l1.8 1.8 3.2-3.6" stroke="white" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <span class="logo-name">AutoQA</span>
            <span class="logo-sub">/ Prompt Optimizer</span>
          </div>
          <span *ngIf="sessionId" class="session-chip">{{ sessionId }}</span>
        </div>
        <div class="stepbar-row">
          <div class="stepbar">
            <ng-container *ngFor="let step of steps; let i = index">
              <div class="step-item">
                <div class="step-circle"
                     [class.done]="step.id < currentStep"
                     [class.active]="step.id === currentStep">
                  {{ step.id < currentStep ? '✓' : step.id }}
                </div>
                <span class="step-label"
                      [class.active]="step.id === currentStep"
                      [class.done]="step.id < currentStep">{{ step.label }}</span>
              </div>
              <div *ngIf="i < steps.length - 1"
                   class="step-connector"
                   [class.done]="step.id < currentStep"></div>
            </ng-container>
          </div>
        </div>
      </div>
      <router-outlet />
    </div>
  `,
  styleUrl: './app.component.css'
})
export class AppComponent implements OnInit, OnDestroy {
  steps = STEPS;
  currentStep = 1;
  sessionId: string | null = null;
  private sub = new Subscription();

  constructor(private router: Router) {}

  ngOnInit() {
    this.sub.add(
      this.router.events
        .pipe(filter(e => e instanceof NavigationEnd))
        .subscribe(() => this.syncFromUrl(this.router.url))
    );
    this.syncFromUrl(this.router.url);
  }

  ngOnDestroy() { this.sub.unsubscribe(); }

  private syncFromUrl(url: string) {
    if (url.startsWith('/results/'))       this.currentStep = 5;
    else if (url.startsWith('/progress/')) this.currentStep = 4;
    else if (url.startsWith('/clarification/')) this.currentStep = 3;
    else if (url.startsWith('/descriptions/')) this.currentStep = 2;
    else this.currentStep = 1;

    const m = url.match(/\/(descriptions|clarification|progress|results)\/([^/?]+)/);
    this.sessionId = m ? m[2] : null;
  }
}
