import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { SessionService } from '../../core/services/session.service';
import { ModelConfig } from '../../core/models/session.model';

const CSV_COLS = [
  { name: 'ConversationID', type: 'string',        desc: 'Unique ID for each conversation row' },
  { name: 'transcript',     type: 'string (JSON)', desc: 'Full agent–customer conversation as a JSON array' },
  { name: '<Metric Name>',  type: 'Yes / No / NA', desc: 'One column per metric — column header is the metric name. NA = not applicable (counted in accuracy; correct only when the AI also predicts NA)' },
];
const CSV_SAMPLE = [
  ['conv_001', '"[{…}]"', 'Yes', 'No',  'NA'],
  ['conv_002', '"[{…}]"', 'No',  'Yes', 'Yes'],
  ['conv_003', '"[{…}]"', 'Yes', 'Yes', 'No'],
];

@Component({
  selector: 'app-upload',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="page">
      <div class="page-header">
        <h1>Upload Evaluation Data</h1>
        <p>Upload a CSV of conversations with ground truth labels. The AI will iteratively refine your evaluation prompts until they reach your accuracy target.</p>
        <div style="text-align:left;max-width:580px;margin:0 auto;">
          <button class="format-toggle" (click)="formatOpen = !formatOpen">
            <span class="arrow" [class.open]="formatOpen">▶</span>
            {{ formatOpen ? 'Hide' : 'View' }} expected CSV format
          </button>
          <div *ngIf="formatOpen" class="format-panel">
            <div class="format-section-label">Required columns</div>
            <div class="col-list">
              <div *ngFor="let c of csvCols" class="col-row">
                <code class="col-name">{{ c.name }}</code>
                <span class="col-type">{{ c.type }}</span>
                <span class="col-desc">{{ c.desc }}</span>
              </div>
            </div>
            <div class="format-section-label">Sample (one row per conversation × parameter)</div>
            <div class="sample-table-wrap">
              <table class="sample-table">
                <thead>
                  <tr>
                    <th *ngFor="let h of ['ConversationID','transcript','Greeting Compliance','Empathy Score','By Question Check']">{{ h }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr *ngFor="let row of csvSample">
                    <td>{{ row[0] }}</td>
                    <td>{{ row[1] }}</td>
                    <td>{{ row[2] }}</td>
                    <td>{{ row[3] }}</td>
                    <td [class.gt-yes]="row[4]==='Yes'" [class.gt-no]="row[4]==='No'" [class.gt-na]="row[4]==='NA'">{{ row[4] }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="format-hint">Wide format — one row per conversation. Add one column per metric.</p>
          </div>
        </div>
      </div>

      <div class="card">
        <!-- Section 1: Evaluation Data -->
        <div>
          <div class="section-label">Evaluation Data</div>
          <div class="field">
            <label>Conversations CSV</label>
            <div class="dropzone"
                 [class.dragging]="dragging"
                 [class.has-file]="!!csvFile"
                 (dragover)="$event.preventDefault(); dragging=true"
                 (dragleave)="dragging=false"
                 (drop)="onDrop($event)">
              <input type="file" accept=".csv" class="dropzone-input" (change)="onFile($event)">
              <div *ngIf="!csvFile" class="drop-placeholder">
                <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
                  <path d="M16 20V10m0-4l-5 5m5-5l5 5" stroke="#9ca3af" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                  <rect x="4" y="22" width="24" height="6" rx="2" fill="#f3f4f6" stroke="#e5e7eb" stroke-width="1.2"/>
                  <text x="16" y="27" text-anchor="middle" font-size="7" fill="#9ca3af" font-family="monospace">.csv</text>
                </svg>
                <p>Drop a .csv file here</p>
                <span>or click to browse</span>
              </div>
              <div *ngIf="csvFile" class="drop-file-info">
                <span class="drop-file-icon">✓</span>
                <div>
                  <div class="drop-file-name">{{ csvFile.name }}</div>
                  <div class="drop-file-sub">{{ (csvFile.size / 1024).toFixed(1) }} KB · Click to replace</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Section 2: Run Configuration -->
        <div>
          <div class="section-label">Run Configuration</div>
          <div class="run-grid">
            <div class="field">
              <label>Max Iterations</label>
              <div class="slider-row">
                <input type="range" min="1" max="10" [(ngModel)]="maxIterations" style="flex:1">
                <span class="slider-val">{{ maxIterations }}</span>
              </div>
              <div class="slider-range"><span>1</span><span>10</span></div>
            </div>
            <div class="field">
              <label>Accuracy Target</label>
              <div class="target-btns">
                <button *ngFor="let t of targets" class="target-btn" [class.active]="accuracyTarget === t" (click)="accuracyTarget = t">
                  {{ t * 100 | number:'1.0-0' }}%
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Section 3: Model Configuration -->
        <div>
          <div class="section-label">Model Configuration</div>

          <!-- Mode selector -->
          <div class="mode-tabs">
            <button class="mode-tab" [class.active]="configMode==='default'" (click)="setMode('default')">
              Default (.env)
            </button>
            <button class="mode-tab" [class.active]="configMode==='custom-key'" (click)="setMode('custom-key')">
              Custom OpenAI Key
            </button>
            <button class="mode-tab" [class.active]="configMode==='custom-endpoint'" (click)="setMode('custom-endpoint')">
              Custom Endpoint
            </button>
          </div>

          <!-- API key field (hidden in default mode) -->
          <div class="field" *ngIf="configMode !== 'default'">
            <label>API Key</label>
            <input class="input" type="password" [(ngModel)]="modelConfig.apiKey" placeholder="sk-…" (ngModelChange)="onConfigChange()">
          </div>

          <!-- Base URL field (custom endpoint only) -->
          <div class="field" *ngIf="configMode === 'custom-endpoint'">
            <label>Base URL</label>
            <input class="input" type="text" [(ngModel)]="modelConfig.baseUrl" placeholder="https://api.openai.com/v1" (ngModelChange)="onConfigChange()">
          </div>

          <!-- Model: dropdown when models are available, text input otherwise -->
          <div class="field">
            <label>Model</label>
            <select class="input" *ngIf="availableModels.length > 0" [(ngModel)]="modelConfig.model" (ngModelChange)="onConfigChange()">
              <option *ngFor="let m of availableModels" [value]="m">{{ m }}</option>
            </select>
            <input class="input mono" type="text" *ngIf="availableModels.length === 0"
                   [(ngModel)]="modelConfig.model" placeholder="gpt-4o" (ngModelChange)="onConfigChange()">
          </div>

          <div class="conn-row">
            <button class="test-btn"
                    [class.success]="connState==='success'"
                    [class.error]="connState==='error'"
                    [disabled]="testing"
                    (click)="testConnection()">
              <span *ngIf="testing" class="spinner"></span>
              <ng-container *ngIf="!testing">
                {{ connState === 'success' ? '✓ Connected' : connState === 'error' ? '✗ Failed' : 'Test Connection' }}
              </ng-container>
              <ng-container *ngIf="testing">Testing…</ng-container>
            </button>
            <span *ngIf="connMessage" class="conn-msg" [class.conn-success]="connState==='success'" [class.conn-error]="connState==='error'">
              {{ connMessage }}
            </span>
          </div>
        </div>

        <!-- CTA -->
        <div>
          <div *ngIf="error" class="error-msg" style="margin-bottom:12px;">{{ error }}</div>
          <button class="cta-btn" [disabled]="!csvFile || loading" (click)="submit()">
            {{ loading ? 'Uploading…' : 'Start Optimization' }} <span style="font-size:1.1rem">→</span>
          </button>
          <p *ngIf="!csvFile" class="cta-hint">Select a CSV file to continue</p>
        </div>
      </div>
    </div>
  `,
  styleUrls: ['./upload.component.css']
})
export class UploadComponent {
  csvFile: File | null = null;
  dragging = false;
  maxIterations = 8;
  accuracyTarget = 0.90;
  targets = [0.70, 0.80, 0.90, 0.95];
  loading = false;
  error = '';
  formatOpen = false;
  csvCols = CSV_COLS;
  csvSample = CSV_SAMPLE;

  modelConfig: ModelConfig = { model: 'gpt-4o', apiKey: '', baseUrl: '' };
  testing = false;
  connState: 'idle' | 'testing' | 'success' | 'error' = 'idle';
  connMessage = '';
  configMode: 'default' | 'custom-key' | 'custom-endpoint' = 'default';
  availableModels: string[] = [];

  constructor(private svc: SessionService, private router: Router) {}

  setMode(mode: 'default' | 'custom-key' | 'custom-endpoint') {
    this.configMode = mode;
    this.availableModels = [];
    this.connState = 'idle';
    this.connMessage = '';
    if (mode === 'default') {
      this.modelConfig = { model: 'gpt-4o', apiKey: '', baseUrl: '' };
    } else if (mode === 'custom-key') {
      this.modelConfig = { model: 'gpt-4o', apiKey: '', baseUrl: '' };
    } else {
      this.modelConfig = { model: '', apiKey: '', baseUrl: '' };
    }
  }

  onConfigChange() {
    this.connState = 'idle';
    this.connMessage = '';
    this.availableModels = [];
  }

  onFile(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) this.csvFile = f;
  }

  onDrop(e: DragEvent) {
    e.preventDefault();
    this.dragging = false;
    const f = e.dataTransfer?.files[0];
    if (f && f.name.endsWith('.csv')) this.csvFile = f;
  }

  testConnection() {
    this.testing = true;
    this.connState = 'idle';
    this.connMessage = '';
    this.svc.validateModelConfig(this.modelConfig).subscribe({
      next: r => {
        this.testing = false;
        if (r.valid) {
          this.connState = 'success';
          this.connMessage = `Connected · ${r.model_used ?? this.modelConfig.model}`;
          if (r.models && r.models.length > 0) {
            this.availableModels = r.models;
            if (!this.availableModels.includes(this.modelConfig.model)) {
              this.modelConfig.model = this.availableModels[0];
            }
          }
        } else {
          this.connState = 'error';
          this.connMessage = r.error ?? 'Validation failed';
        }
      },
      error: e => {
        this.testing = false;
        this.connState = 'error';
        this.connMessage = e.error?.detail ?? 'Connection test failed';
      }
    });
  }

  submit() {
    if (!this.csvFile) return;
    this.loading = true;
    this.error = '';
    this.svc.createSession(this.csvFile, this.maxIterations, this.accuracyTarget, 'en', this.modelConfig)
      .subscribe({
        next: r => this.router.navigate([`/descriptions/${r.session_id}`]),
        error: e => { this.error = e.error?.detail || 'Upload failed'; this.loading = false; }
      });
  }
}
