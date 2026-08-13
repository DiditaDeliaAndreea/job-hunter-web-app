# CareerMatch

CareerMatch is a CV-powered job search dashboard. Upload one or more CVs, configure target and excluded roles, search recent opportunities, review match explanations, inspect full job descriptions, and track application status.

## Features

- Upload multiple PDF or DOCX CVs.
- Reuse saved CV analysis for later searches.
- Configure and save target or excluded roles locally in the browser.
- Search jobs with Gemini Google Search and optional OpenAI fallback.
- Prefer official employer listings and preserve original job-board URLs.
- Save results incrementally to `data/job_matches.csv` after each batch.
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
- `data/job_matches.csv`: local persisted job data; intentionally excluded from GitHub.
- `tests/`: regression tests.

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
```

`OPENAI_API_KEY` is optional. The app uses Gemini first and tries OpenAI after the first Gemini failure when the key is configured.

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

- Job records are stored locally in `data/job_matches.csv`.
- Uploaded CVs used for browser previews are stored in browser IndexedDB.
- API keys are loaded from `.env` and must never be committed or pasted into public files.
- Rotate any API key that has been exposed.
- The CSV may contain personal or job-search data; review it before publishing the repository.

## API Endpoints

- `POST /api/search/start`: start a multi-CV search.
- `GET /api/search/status/{search_id}`: poll search progress and logs.
- `GET /api/search/result/{search_id}`: retrieve the generated workbook.
- `GET /api/jobs`: load active CSV-backed jobs.
- `POST /api/jobs/verify/start`: verify saved jobs against current listings.
- `POST /api/jobs/dismiss`: persist a dismissed job.
- `POST /api/jobs/applied`: persist application status.
- `POST /api/jobs/update-url`: update a preferred listing URL.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for known startup, model, rate-limit, CSV, URL, and partial-result issues.

## Security Before Publishing

Before pushing to GitHub:

1. Confirm `.env` is ignored.
2. Rotate any previously exposed Google or OpenAI keys.
3. Keep `data/job_matches.csv` private; it is intentionally excluded from the public repository.
4. Remove local environments and generated folders from the repository if they are present: `.venv312`, `node_modules`, and `.next`.
5. Keep `package-lock.json`, `requirements.txt`, and application source files.
