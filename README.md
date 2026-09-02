# CareerMatch

CareerMatch is a CV-powered job search dashboard. Upload one or more CVs, configure target and excluded roles, search recent opportunities, review match explanations, inspect full job descriptions, and track application status.

## Features

- Upload multiple PDF or DOCX CVs.
- Reuse saved CV analysis for later searches.
- Configure and save target or excluded roles locally in the browser.
- Search jobs via structured job-search APIs (Adzuna, JSearch, optionally Jooble), then score results with AI against your CV.
- Prefer official employer listings and preserve original job-board URLs.
- Save results incrementally after each search batch.
- Persist jobs in Firebase Firestore when Firebase environment variables are configured; otherwise use the local CSV.
- View job descriptions, match reasons, recommended CVs, tailoring guidance, salary, and URL status.
- Edit preferred job URLs from the details page.
- Mark jobs as applied.
- Dismiss irrelevant or old jobs without allowing them to be re-added.
- Filter by keyword, working type, salary availability, posted date, and match score.
- Verify saved jobs against official company websites.
- Export the visible CSV-backed jobs to Excel from the dashboard.

## Architecture

- `app/`: Next.js frontend.
- `api/index.py`: FastAPI backend, CV parsing, AI orchestration, search polling, verification, and exports.
- `utils/`: CSV import, normalization, deduplication, and user-status persistence.
- `data/job_matches.csv`: local fallback job data; intentionally excluded from GitHub.
- `tests/`: regression tests.
- `scripts/`: one-off migration and maintenance scripts.
- `docs/`: troubleshooting and operational notes.

## Requirements

- Node.js 18 or newer.
- Python 3.12 recommended.
- A Google API key for Gemini and Google Search.
- An OpenAI API key is optional and used as fallback when Gemini fails.

## Local Setup

### 1. Install frontend dependencies

```powershell
npm install
```

### 2. Create or activate the Python environment

The project uses `.venv312` in the existing local setup. Create a new environment if needed:

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure environment variables

Create `.env` in the project root. Never commit it.

```env
GOOGLE_API_KEY=your-google-api-key
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4.1-mini
# Optional structured CV extraction provider: gemini (default), openai, or anthropic
CV_EXTRACTION_PROVIDER=gemini
OPENAI_EXTRACTION_MODEL=gpt-4o-mini
ANTHROPIC_API_KEY=your-anthropic-api-key
ANTHROPIC_EXTRACTION_MODEL=claude-3-5-sonnet-latest
# Structured job sources used for job discovery. Use any of "adzuna", "jsearch", "jooble".
JOB_AGGREGATORS=adzuna,jsearch
ADZUNA_APP_ID=your-adzuna-app-id
ADZUNA_APP_KEY=your-adzuna-app-key
RAPIDAPI_KEY=your-rapidapi-key
JOOBLE_API_KEY=your-jooble-api-key
# AI provider used only to score/explain jobs already returned by the APIs above.
JOB_MATCH_PROVIDER=openai
OPENAI_MATCH_MODEL=gpt-4o-mini
FIREBASE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"your-project-id"}
FIREBASE_STORAGE_BUCKET=your-project.firebasestorage.app
NEXT_PUBLIC_FIREBASE_API_KEY=your-web-api-key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project-id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your-project.firebasestorage.app
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=your-messaging-sender-id
NEXT_PUBLIC_FIREBASE_APP_ID=your-web-app-id
NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID=your-measurement-id
```

Set `CV_EXTRACTION_PROVIDER=openai` to use GPT-4o-mini for CV structuring, or
`CV_EXTRACTION_PROVIDER=anthropic` to use Claude for complex multi-page layouts.
The default remains Gemini so existing deployments do not change behavior.

Job discovery is API-only: set `JOB_AGGREGATORS=adzuna,jsearch` with the
matching API keys to fetch listings. There is no AI-based job search — Gemini
and OpenAI are never used to find or invent listings, only to score the jobs
the APIs return. Aggregator results still pass through the existing
duplicate, description, and dead-link validation, and freshness is enforced
from each provider's own posting timestamp (not an AI guess), using the
search's configured "posted within" days.

Add `jooble` to `JOB_AGGREGATORS` and set `JOOBLE_API_KEY` to include Jooble
as a third source; its listings carry an `updated` timestamp used the same
way for freshness filtering. Jooble's free tier issues one key per country
and caps each key at 500 lifetime requests, so keep it as a supplementary
source alongside Adzuna/JSearch rather than your only aggregator.

Adzuna has no Ireland index. Its supported country codes are `at, au, be,
br, ca, ch, de, es, fr, gb, in, it, mx, nl, nz, pl, sg, us, za` — `ie`
always fails with `UNSUPPORTED_COUNTRY`. `ADZUNA_COUNTRY` defaults to `gb`
(the closest supported market); set it explicitly if you're targeting a
different supported country. Unsupported values are skipped with a warning
instead of failing the whole search.

Set `JOB_MATCH_PROVIDER=openai` (default) or `gemini` to choose which AI
provider scores fetched jobs against the candidate CV — computing the fit
score, match reasons, missing requirements, extracted skills, and the
recommended CV/tailoring guidance. This AI step never searches for jobs; it
only evaluates the fixed set of listings the configured job APIs returned.

`OPENAI_API_KEY` is optional. The app uses Gemini first and tries OpenAI after the first Gemini failure when the key is configured.

To enable hosted job persistence, create a Firebase project, enable Firestore, download a service-account key, and set `FIREBASE_SERVICE_ACCOUNT_JSON` to the key's JSON contents. The backend uses the Admin SDK only; keep this value server-side and never expose it to the browser. Without it, the app continues using the local CSV.

The `NEXT_PUBLIC_FIREBASE_*` values initialize the browser SDK and Analytics. They are not a replacement for the server-only service-account JSON.

In the Firebase console, enable **Authentication > Sign-in method > Email/Password**. Registration and sign-in are handled by the browser SDK. For Firebase-backed data, download a service-account JSON key and add its complete one-line JSON value to the backend `.env` as `FIREBASE_SERVICE_ACCOUNT_JSON`, plus the project's Storage bucket as `FIREBASE_STORAGE_BUCKET`. The API verifies each user's ID token, stores jobs under `users/{uid}/jobs`, stores CV metadata under `users/{uid}/cvs`, and stores the PDF/DOCX bytes in Firebase Storage.

Alternatively, keep the downloaded key as a local file and set `GOOGLE_APPLICATION_CREDENTIALS` to its path. The Node.js `firebase-admin` example using `require("serviceAccountKey.json")` is equivalent, but this project uses the Python Firebase Admin SDK.

CV workspace prompts are saved under `users/{uid}/prompt_preferences` and included as recent style preferences in later tailoring requests. This is retrieval-based personalization, not live model fine-tuning; the underlying AI model is unchanged.

### 4. Start the backend

```powershell
.\.venv312\Scripts\python.exe -m uvicorn api.index:app --host 0.0.0.0 --port 8000
```

### 5. Start the frontend

In a second terminal:

```powershell
npm run dev -- --hostname 0.0.0.0 --port 3000
```

Open http://localhost:3000.

## Production Build

```powershell
npm run build
npm run start
```

The backend remains a separate FastAPI service and must also be deployed/configured separately.

## Data and Privacy

- Job records are stored in Firebase Firestore when configured, or locally in `data/job_matches.csv` as a fallback.
- Uploaded CVs used for browser previews are stored in browser IndexedDB.
- API keys are loaded from `.env` and must never be committed or pasted into public files.
- Rotate any API key that has been exposed.
- The CSV may contain personal or job-search data; review it before publishing the repository.

## API Endpoints

- `POST /api/search/start`: start a multi-CV search.
- `GET /api/search/status/{search_id}`: poll search progress and logs.
- `GET /api/search/result/{search_id}`: retrieve the generated workbook.
- `GET /api/jobs`: load active persisted jobs.
- `POST /api/jobs/verify/start`: verify saved jobs against current listings.
- `POST /api/jobs/dismiss`: persist a dismissed job.
- `POST /api/jobs/applied`: persist application status.
- `POST /api/jobs/update-url`: update a preferred listing URL.

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for known startup, model, rate-limit, CSV, URL, and partial-result issues.

## Security Before Publishing

Before pushing to GitHub:

1. Confirm `.env` is ignored.
2. Rotate any previously exposed Google or OpenAI keys.
3. Keep `data/job_matches.csv` private; it is intentionally excluded from the public repository.
4. Remove local environments and generated folders from the repository if they are present: `.venv312`, `node_modules`, and `.next`.
5. Keep `package-lock.json`, `requirements.txt`, and application source files.
