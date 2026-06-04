import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'upload', pathMatch: 'full' },
  { path: 'upload', loadComponent: () => import('./pages/upload/upload.component').then(m => m.UploadComponent) },
  { path: 'descriptions/:sessionId', loadComponent: () => import('./pages/descriptions/descriptions.component').then(m => m.DescriptionsComponent) },
  { path: 'clarification/:sessionId', loadComponent: () => import('./pages/clarification/clarification.component').then(m => m.ClarificationComponent) },
  { path: 'progress/:sessionId', loadComponent: () => import('./pages/progress/progress.component').then(m => m.ProgressComponent) },
  { path: 'results/:sessionId', loadComponent: () => import('./pages/results/results.component').then(m => m.ResultsComponent) },
];
