# CareerMatch Project History

## Project snapshot

CareerMatch is a CV-powered job-search dashboard built with a Next.js frontend and a FastAPI backend. The current app is centered on a signed-in user workflow: upload CVs, save them to Firebase Storage, set target and excluded roles, run AI-assisted job searches, review matches, and manage jobs through an authenticated account.

## Current architecture

- `app/`: Next.js App Router frontend, pages, navigation, and user screens.
- `api/index.py`: FastAPI backend for CV upload, AI search orchestration, Firebase-authenticated endpoints, and job persistence.
- `lib/api.ts`: frontend request layer that includes the Firebase ID token on authenticated API calls.
- `lib/firebase.ts`: Firebase web client initialization and analytics setup.
- `utils/firebase_utils.py`: Firebase Admin SDK logic for Firestore, Storage, jobs, CV metadata, and prompt personalization.
- `utils/csv_utils.py`: CSV fallback and migration/normalization helpers retained for local compatibility and testing.
- `utils/browserStorage.ts`: browser-side local CV cache used for faster preview and offline fallback.
- `firebase/`: Firestore rules and indexes.
- `scripts/`: import and maintenance scripts.
- `docs/`: project history, troubleshooting, and user documentation.

## Product evolution

### Firebase-backed user workflow

The project evolved from a local CSV-first workflow into a per-user Firebase-backed app. The main user lifecycle now includes:

- registration and sign-in via Firebase Email/Password
- authenticated API requests using Firebase ID tokens
- user-scoped Firestore records for jobs, CV metadata, and prompt preferences
- Firebase Storage for uploaded PDF and DOCX files
- per-user privacy boundaries enforced by Firestore rules

The app enforces the signed-in user path pattern:

```text
users/{uid}/jobs/{job_id}
users/{uid}/cvs/{cv_id}
users/{uid}/prompt_preferences/{preference_id}
```

## User-facing functionality

### Search and shortlist flow

The main dashboard now focuses on a simple, end-to-end job search process:

1. Sign in.
2. Upload or select CVs.
3. Set target and excluded role preferences.
4. Start a search across recent opportunities.
5. Review the resulting job cards and open-job list.
6. Open a job detail page to inspect match reasoning and tailoring options.

### Job management

Users can:

- mark jobs as applied or not applied
- mark jobs as active or expired
- dismiss or delete jobs
- update the preferred listing URL
- inspect job descriptions and match explanations
- view a recommended CV and tailoring workspace on each job page

### CV management

The CV experience includes:

- PDF and DOCX uploads
- saved CV metadata in Firestore
- browser preview for uploaded files
- DOCX-to-HTML conversion with Mammoth for previewing documents
- selection of one or more saved CVs for a search
- renaming or deletion of CV records

### Personalization and tailoring

The job detail workspace supports direct tailoring and Q&A. Every non-empty prompt is saved automatically and re-used as recent preference context in later AI requests. This is a retrieval-based personalization pattern instead of a model fine-tuning workflow.

## UI and navigation changes

Major UX iterations included:

- collapsible left navigation
- responsive job cards instead of dense tables
- plain-language labels for the main tasks
- bigger CV preview regions
- a more direct Open jobs flow after search completion
- Job preferences managed as removable pills with simple role-entry behavior
- clearer Account and privacy screens

## Operational history

### Firebase setup and delivery

The project was configured to use Firebase for hosting, storage, auth, and user data. The app expects:

- a Firebase project with Auth enabled
- Storage enabled in the Firebase Console
- Firestore enabled for user data
- service account credentials for the backend only
- browser Firebase config keys for the frontend web SDK

### Environment expectations

The backend uses service-account credentials or `GOOGLE_APPLICATION_CREDENTIALS`. The frontend uses `NEXT_PUBLIC_FIREBASE_*` values. Sensitive keys and JSON credentials are never committed to the repository.

### Troubleshooting and stabilization

Key issues fixed during the project lifecycle included:

- missing Firebase Admin credentials causing API failures
- missing Storage buckets causing CV upload errors
- repeated Firebase Admin initialization warnings
- stale backend processes after route changes
- Windows Firebase CLI login issues requiring `--no-localhost`
- partial search result loss when a later batch failed
- automatic CSV overwrite problems during empty-result scenarios

## Validation and current state

The project has been validated through repeated local checks, including:

- frontend build validation
- backend syntax validation
- targeted regression tests around CSV status handling and partial-result persistence
- Firebase rules deployment
- authenticated flow validation for user-scoped job and CV storage

## Current follow-ups

- confirm Firebase Storage remains enabled in production
- verify the service account JSON remains outside the repository
- continue smoke testing registration, CV upload, job search, and tailoring flows
- consider a future cross-device sync option for role preferences

## Project note

This file documents the project’s current direction and key milestones. For operational issues and day-to-day troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md). For practical end-user instructions, see [USER_GUIDE.md](USER_GUIDE.md).
