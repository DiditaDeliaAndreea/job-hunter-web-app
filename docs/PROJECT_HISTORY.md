# CareerMatch Project History

## Overview

CareerMatch is a CV-powered job search dashboard with a Next.js frontend and a FastAPI backend. The app now uses Firebase for authentication, Firestore for user-scoped records, and Firebase Storage for uploaded CV files.

## Architecture

- `app/`: Next.js App Router frontend and user interface.
- `api/index.py`: FastAPI backend, CV parsing, AI search, verification, exports, authentication, and Firebase-backed endpoints.
- `lib/firebase.ts`: Firebase Web SDK initialization and Analytics.
- `lib/api.ts`: authenticated frontend requests with Firebase ID tokens.
- `utils/firebase_utils.py`: Firebase Admin SDK, Firestore, Storage, CV files, jobs, and prompt preferences.
- `utils/csv_utils.py`: CSV fallback, normalization, deduplication, and migration support.
- `utils/browserStorage.ts`: local browser CV copies used by the job-detail CV workspace.
- `app/navigation.tsx`: collapsible application navigation.
- `app/job-list.tsx`: shared Open Jobs and Applied Jobs card view.
- `firebase/`: Firestore rules and indexes.
- `scripts/`: maintenance and migration scripts.
- `docs/`: project history and troubleshooting notes.

## Firebase Setup

Firebase project:

- Project ID: `cloud-gif-search-portfolio`
- Hosting site: `job-hunter-3d937`
- Hosting URL: https://job-hunter-3d937.web.app
- Firestore location: `eur3`

Firebase CLI files:

- `.firebaserc`: associates the repository with the Firebase project.
- `firebase.json`: points Hosting to `job-hunter-3d937` and Firestore to `firebase/firestore.rules` and `firebase/firestore.indexes.json`.
- `firebase/firestore.rules`: per-user access rules.
- `firebase/firestore.indexes.json`: Firestore indexes.

The Firebase CLI was installed and authenticated. Firestore rules were deployed successfully.

## Environment Configuration

The backend `.env` uses a downloaded service-account JSON file:

```env
GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\serviceAccountKey.json
FIREBASE_STORAGE_BUCKET=cloud-gif-search-portfolio.firebasestorage.app
```

The frontend uses `NEXT_PUBLIC_FIREBASE_*` values in `.env.local` for the Web SDK and Analytics.

Never commit `.env`, `.env.local`, service-account JSON files, API keys, or private keys.

## Authentication

Added Firebase Email/Password registration and sign-in:

- `app/auth-provider.tsx` provides auth state and the sign-in/register screen.
- `app/layout.tsx` protects the application behind the authenticated provider.
- `lib/api.ts` sends the Firebase ID token in the `Authorization: Bearer ...` header.
- `api/index.py` verifies Firebase ID tokens with Firebase Admin.
- The Account page shows the account email and privacy information, not the internal Firebase UID.

Firebase Console requirement:

- Enable Authentication > Sign-in method > Email/Password.

## Firestore Data Model

Jobs:

```text
users/{uid}/jobs/{job_id}
```

CV metadata:

```text
users/{uid}/cvs/{cv_id}
```

Prompt preferences:

```text
users/{uid}/prompt_preferences/{preference_id}
```

Firestore rules restrict reads and writes to the signed-in user's own UID path.

## Job Persistence

Jobs are stored in Firestore when the backend receives an authenticated user ID and Firebase is configured. The current job operations include:

- Search result saving.
- Existing CSV migration.
- Open job loading.
- Applied/not-applied status.
- Active/expired status.
- Dismissal/removal.
- Preferred URL updates.
- Verification results.

The local CSV was removed after migration because Firebase is now the active store. The CSV utility still contains a fallback for tests and local fallback usage.

Migration endpoint:

```text
POST /api/jobs/import-csv
```

It imports the existing `data/job_matches.csv` into the signed-in user's Firestore jobs. The old CSV was later removed locally after the Firebase migration.

## CV Management

CV files are saved through the backend:

- Metadata is stored in Firestore.
- PDF/DOCX bytes are stored in Firebase Storage under `users/{uid}/cvs/...`.
- CVs can be selected for a search.
- CVs can be renamed.
- CVs can be removed from Firestore and Storage.
- The My CVs page displays saved CVs in a left list and opens the selected CV in a larger right-side preview.
- PDFs preview in an iframe.
- DOCX files are converted to HTML with Mammoth and shown in the preview panel.

Required backend services:

- Firestore enabled.
- Firebase Storage enabled by clicking Storage > Get started in Firebase Console.

## AI Tailoring Personalization

The CV workspace supports tailoring and direct questions. Every non-empty user prompt is saved automatically; there is no separate save button.

Prompts are stored in `users/{uid}/prompt_preferences` and recent prompts are included as style context in later tailoring requests. This is retrieval-based personalization, not live model fine-tuning.

The tailoring flow:

1. User selects a recommended CV.
2. User enters a tailoring instruction or question.
3. The backend saves the prompt.
4. The backend includes recent user preferences in the AI request.
5. The response is returned to the CV workspace.

## Navigation and Pages

The application has a collapsible navigation menu. It starts collapsed and expands when the menu button is clicked.

Pages:

- `/`: Find jobs and start a search.
- `/open-jobs`: Open job cards and saved-job checking.
- `/applied-jobs`: Applied job cards.
- `/cvs`: CV upload, rename, remove, and preview.
- `/preferences`: Target and excluded role pills.
- `/stats`: Job and application statistics.
- `/account`: Account email and privacy information.
- `/jobs/[id]`: Full job details, tailored CV workspace, and job actions.

The main search page no longer displays large job tables. When a search completes, it links the user to Open jobs.

## Job Preferences

Target and excluded roles are displayed as removable pills:

- Press Enter or comma to add a role.
- Click a pill to remove it.
- Pasted comma-separated or newline-separated roles are split automatically.
- Surrounding single or double quotation marks are removed automatically.
- Preferences are currently stored in browser local storage under `careermatch-role-preferences`.

## Job Cards and Actions

Open Jobs and Applied Jobs use responsive cards instead of table rows. Cards show:

- Title.
- Company.
- Location.
- Working type.
- Match score.
- Status.
- Details link.
- Original listing link when available.

Expired status pills are red. Active status pills are green. Applied pills are green.

Job detail actions:

- Mark applied/not applied.
- Mark active/expired.
- Delete/dismiss with confirmation.
- Edit the preferred listing URL.

Open jobs also contains the saved-job checking workflow with progress and live logs.

## UI Improvements

Recent usability work included:

- Collapsible side navigation.
- Responsive job cards.
- Wider Job Preferences sections with more spacing.
- Larger CV preview area.
- Plain-language labels replacing technical wording such as pipeline, workspace, and ATS-facing text.
- Improved Account page layout to prevent awkward wrapping.
- Clear search completion link to Open jobs.

## Troubleshooting History

### Firebase Admin credentials missing

Symptom: `/api/jobs` and `/api/cvs` returned `503`.

Cause: the backend did not have `FIREBASE_SERVICE_ACCOUNT_JSON` or `GOOGLE_APPLICATION_CREDENTIALS`.

Fix: configure the service-account JSON path in `.env` and restart FastAPI.

### Firebase Storage bucket missing

Symptom: CV upload returned a Google Storage 404.

Cause: Firebase Storage had not been provisioned and the configured bucket did not exist.

Fix: open Firebase Console > Storage and click Get started.

### Firebase Admin initialized twice

Symptom: concurrent jobs and CV requests produced a default-app initialization warning.

Fix: added a lock around one-time Firebase Admin initialization in `utils/firebase_utils.py`.

### Firebase login Windows callback crash

The standard Firebase CLI browser callback crashed under Node 24 on Windows. The manual `firebase login --no-localhost` flow worked, and the CLI was authenticated successfully.

### Stale backend process

After adding routes, the running FastAPI process needed to be stopped and restarted so new endpoints such as `/api/jobs/import-csv` and CV endpoints were loaded.

## Cleanup and Organization

- Removed the empty `supabase/` directory.
- Moved `TROUBLESHOOTING.md` to `docs/TROUBLESHOOTING.md`.
- Moved `run_import.py` to `scripts/run_import.py`.
- Moved Firebase rules and indexes under `firebase/` and updated `firebase.json` paths.
- Removed the local `data/` folder after Firebase became the active job store.
- Removed generated `tsconfig.tsbuildinfo`.
- Added ignore rules for caches, coverage, logs, Firebase local state, OS metadata, and package-manager debug logs.
- `.next`, `node_modules`, `.venv312`, `.pytest_cache`, `__pycache__`, and `.vercel` remain local/generated and are ignored.
- The repository was pushed to GitHub on `main` in commit `0a01fe9`.

## Validation History

Validated repeatedly during the work:

- `npm run build` passed after the final UI changes.
- `python -m py_compile api/index.py utils/firebase_utils.py` passed.
- `tests/test_csv_status_update.py` passed.
- Partial-results persistence test passed after preserving optional local CSV compatibility.
- Firebase rules deployed successfully.

## Useful Commands

Start backend:

```powershell
.venv312\Scripts\python.exe -m uvicorn api.index:app --host 0.0.0.0 --port 8000
```

Start frontend:

```powershell
npm run dev -- --hostname 0.0.0.0 --port 3000
```

Build frontend:

```powershell
npm run build
```

Run Python tests:

```powershell
.venv312\Scripts\python.exe -m pytest
```

## Current Follow-ups

- Commit and push the latest changes made after commit `0a01fe9` if desired.
- Confirm Firebase Storage is enabled in the Firebase Console.
- Keep the service-account JSON outside the repository.
- Consider moving role preferences from local storage to Firestore for cross-device sync.
- Run a full authenticated smoke test for registration, CV upload, preview, rename, delete, job search, and prompt personalization.

## Obsidian Notes

This file is plain Markdown and can be opened as an Obsidian note. The repository itself can be added as an Obsidian vault, or the `docs/` folder can be opened as a vault if you prefer a smaller documentation view.
