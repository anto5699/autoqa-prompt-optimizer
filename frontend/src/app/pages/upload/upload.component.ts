import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { SessionService } from '../../core/services/session.service';

@Component({
  selector: 'app-upload',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="page">
      <h1>AutoQA Prompt Optimizer</h1>
      <div class="card">
        <h2>Upload Evaluation Data</h2>

        <div class="field">
          <span class="field-label">Conversations CSV</span>
          <div class="dropzone" (dragover)="$event.preventDefault()" (drop)="onDrop($event)">
            <span>{{ csvFile ? csvFile.name : 'Click or drag a .csv file here' }}</span>
            <input type="file" accept=".csv" class="dropzone-input" (change)="onFile($event)">
          </div>
        </div>

        <div class="row">
          <div class="field">
            <label>Max Iterations</label>
            <input type="number" [(ngModel)]="maxIterations" min="1" max="10">
          </div>
          <div class="field">
            <label>Accuracy Target</label>
            <input type="number" [(ngModel)]="accuracyTarget" min="0.1" max="1" step="0.05">
          </div>
        </div>

        <div *ngIf="error" class="error">{{ error }}</div>

        <button [disabled]="!csvFile || loading" (click)="submit()">
          {{ loading ? 'Uploading…' : 'Start Optimization' }}
        </button>
      </div>
    </div>
  `,
  styleUrls: ['./upload.component.css']
})
export class UploadComponent {
  csvFile: File | null = null;
  maxIterations = 8;
  accuracyTarget = 0.90;
  loading = false;
  error = '';

  constructor(private svc: SessionService, private router: Router) {}

  onFile(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) this.csvFile = f;
  }

  onDrop(e: DragEvent) {
    e.preventDefault();
    const f = e.dataTransfer?.files[0];
    if (f) this.csvFile = f;
  }

  submit() {
    if (!this.csvFile) return;
    this.loading = true;
    this.error = '';
    this.svc.createSession(this.csvFile, this.maxIterations, this.accuracyTarget, 'en')
      .subscribe({
        next: r => this.router.navigate([`/descriptions/${r.session_id}`]),
        error: e => { this.error = e.error?.detail || 'Upload failed'; this.loading = false; }
      });
  }
}
