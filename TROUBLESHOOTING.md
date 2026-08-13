# Job Hunter App Troubleshooting Guide

This file captures the major issues, fixes, and lessons learned while building and debugging the local CV-to-job-search application.

## 1. Project Overview

- Frontend: Next.js app running on localhost:3000
- Backend: FastAPI + Uvicorn running on localhost:8000
- AI model: Google Gemini via CrewAI / Google GenAI SDK
- Data persistence: CSV export/import under the data/ folder
- Job export: Excel workbook generated from saved CSV rows
- Primary workflow: upload CV -> parse -> analyze profile -> search jobs -> save results -> show jobs in UI

## 2. Common Startup and Port Problems

### Issue: Backend port 8000 already in use
Symptoms:
- Uvicorn fails with `OSError: [Errno 10048] only one usage of each socket address`.
- App appears to start but then crashes while binding to port 8000.

What fixed it:
- Stop stale background processes from previous runs.
- Re-run the backend cleanly with:
  - `.\.venv312\Scripts\python.exe -m uvicorn api.index:app --host 0.0.0.0 --port 8000`
- Same approach should be used for the frontend if port 3000 is stuck:
  - `npm run dev -- --hostname 0.0.0.0 --port 3000`

### Issue: Frontend could not connect to backend
Symptoms:
- Browser requests fail.
- UI not loading data or API calls return 404/connection issues.

What fixed it:
- Ensure both apps are running on the expected hosts/ports.
- Confirm FastAPI CORS allows localhost:3000.
- Confirm the status routes exist before the frontend polls them.

## 3. Environment and API Key Problems

### Issue: `GOOGLE_API_KEY` missing or not loaded
Symptoms:
- App starts but no AI results are returned.
- Gemini calls fail or app silently falls back to empty placeholder rows.

What fixed it:
- Confirm the key is present in `.env`.
- Ensure `.env` is in the project root and the process loads it using `python-dotenv`.
- The app validates this at startup via `validate_environment()`.

### Issue: Invalid or outdated model name
Symptoms:
- Requests reach the API but fail with 404 model not found / model unavailable.
- Example: `gemini-2.0-flash` or stale `gemini-flash-latest` style names may be rejected depending on the account / API version.

What fixed it:
- Keep the model name aligned with current supported Gemini model aliases.
- Use a working model name supported by the active Gemini API account.
- Verify by a direct test before relying on it in production.

### Issue: Gemini temporarily returns 503 or 429 errors

What fixed it:
- Add `OPENAI_API_KEY` to `.env` to enable the optional fallback provider.
- The app tries OpenAI only after Gemini retries are exhausted.
- CV analysis uses a normal OpenAI response; job batches use OpenAI web search.
- Set `OPENAI_MODEL` to change the fallback model, defaulting to `gpt-4.1-mini`.

## 4. PDF / DOCX CV Parsing Problems

### Issue: DOCX files not parsing correctly at first
Symptoms:
- CV text extraction fails or produces empty content.
- The app rejects files or generates poor matching data.

What fixed it:
- Use `python-docx` to parse DOCX and `pypdf` for PDF.
- Validate that extracted text is non-empty.
- Reject corrupted or unreadable files with clear HTTP 422 messages.

### Issue: Empty CV content
Symptoms:
- The model receives no usable content.
- Search results are empty or invalid.

What fixed it:
- Reject blank or unreadable uploads.
- Log the extraction step and fail clearly instead of continuing with nonsense input.

## 5. Long-running AI Search and UI Behavior

### Issue: App looked stuck during a long search
Symptoms:
- The UI showed no progress for a long time.
- The user thought the app had frozen.

What fixed it:
- Added live status polling endpoints:
  - `/api/search/start`
  - `/api/search/status/{search_id}`
  - `/api/search/result/{search_id}`
- Added a frontend progress bar and log stream.
- Added per-batch progress messages such as:
  - `Batch 1: found 4 jobs.`
  - `Batch 2: no jobs found.`
  - `Search interrupted after batch 3: ...`

## 6. Gemini Rate Limits and Transient Failures

### Issue: Google returned 503 / rate limit / server busy
Symptoms:
- Search job batches fail abruptly.
- User sees empty or partial results.

What fixed it:
- Added retry logic with increasing backoff.
- Batched role searches into smaller groups.
- Treated partial results as valid and preserved them if later batches fail.

### Issue: Search failed after some results were already found
Symptoms:
- Previously found jobs were lost because the whole workflow was treated as failed.

What fixed it:
- Save partial results incrementally.
- Keep valid earlier matches even if later batches fail.
- Do not overwrite a valid CSV with a fake placeholder row such as:
  - `No matches found, N/A, ...`

## 7. CSV / Excel Export Problems

### Issue: CSV was overwritten with a placeholder row
Symptoms:
- The file in `data/job_matches.csv` showed a fake result like `No matches found`.
- Frontend then displayed incorrect or empty data.

What fixed it:
- Guarded against empty or invalid search payloads.
- Kept previous valid CSV rows rather than replacing them with placeholder results.
- Appended unique jobs instead of overwriting the dataset.

### Issue: Search results were saved only when everything was complete
Symptoms:
- If a later batch failed, all prior results were lost.

What fixed it:
- Partial valid data is preserved.
- CSV writing only skips when there is genuinely no valid data to persist.

### Issue: Excel export was triggered automatically
Symptoms:
- Download started immediately after the search completed without user action.

What fixed it:
- Removed the automatic browser download.
- The UI now keeps the ready result and only downloads when the user clicks the button.

## 8. Job Filtering Requirements

### Intended behavior
The app was designed to search for jobs that are:
- relevant to target roles
- in Dublin, Ireland
- active and not older than one week
- high-fit matches for the candidate profile

### Important caveat
The code instructed the model to filter by recency and relevance, but the strict minimum threshold of 70% fit score was not enforced at the Python layer unless explicitly added later.

## 9. Final Lessons Learned

- Always confirm the real model name before trusting AI output.
- Keep partial result preservation in the search pipeline.
- Do not overwrite valid CSV data with empty-result placeholders.
- Use status polling and live logs for long-running AI workflows.
- Keep the frontend resilient to JSON errors and partial states.
- Protect exports and CSV persistence from empty or invalid job payloads.
- Respect a user’s preference for manual download instead of automatic file saving.

## 10. Useful Commands

### Backend
```powershell
cd C:\Users\delia\Documents\GitHub\job_hunter_app\job_hunter_app
.\.venv312\Scripts\python.exe -m uvicorn api.index:app --host 0.0.0.0 --port 8000
```

### Frontend
```powershell
cd C:\Users\delia\Documents\GitHub\job_hunter_app\job_hunter_app
npm run dev -- --hostname 0.0.0.0 --port 3000
```

### Build validation
```powershell
cd C:\Users\delia\Documents\GitHub\job_hunter_app\job_hunter_app
.\.venv312\Scripts\python.exe -m compileall api/index.py
npm run build
```

## 11. Key Files

- `api/index.py` — backend orchestration, AI calls, progress state, CSV/Excel logic
- `app/page.tsx` — frontend progress UI and polling logic
- `utils/csv_utils.py` — CSV import/export and deduping behavior
- `data/job_matches.csv` — persisted job results
- `.env` — project environment configuration including API key

## 12. Current State

The app currently works as a local prototype for:
- CV upload
- AI candidate analysis
- live job search progress
- partial result persistence
- CSV/Excel export triggered only by direct user action
