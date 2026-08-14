import asyncio
import hashlib
import io
import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
import urllib.error
import urllib.request
from html import unescape
from typing import Any, Dict, List
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pypdf import PdfReader
from docx import Document

# Import CSV utilities
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.csv_utils import append_jobs_to_csv, dismiss_job_in_csv, import_jobs_from_csv, update_job_applied_in_csv, update_job_status_in_csv, update_job_url_in_csv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load local environment variables (.env)
load_dotenv()

@asynccontextmanager
async def validate_environment(_: FastAPI):
    """Validate required environment variables during application startup."""
    required_keys = ["GOOGLE_API_KEY"]
    missing = [key for key in required_keys if not os.getenv(key)]

    if missing:
        error_msg = f"Missing required environment variables: {', '.join(missing)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    logger.info("Environment variables validated")
    logger.info("Direct Google GenAI client ready")
    if os.getenv("OPENAI_API_KEY"):
        logger.info("OpenAI fallback configured")

    yield


app = FastAPI(lifespan=validate_environment)

# Add CORS middleware to allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# TARGET AND EXCLUDED ROLES CONFIGURATION
# ============================================================================

TARGET_ROLES = [
    "Technical Solutions Consultant", "Technical Support Engineer", "Technical Support Specialist",
    "Product Support Engineer", "Application Support Engineer", "Application Support Specialist",
    "Solutions Engineer", "Solutions Consultant", "Technical Consultant", "Technical Systems Specialist",
    "Systems Support Engineer", "Customer Support Engineer", "Customer Solutions Engineer",
    "Product Support Specialist", "AI Support Specialist", "AI Support Engineer", "AI Operations Specialist",
    "AI Operations Analyst", "AI Quality Analyst", "AI Quality Assurance Engineer", "AI/ML Quality Analyst",
    "Generative AI Support Specialist", "Technical Operations Specialist", "Technical Operations Analyst",
    "Product Operations Specialist", "Product Operations Analyst", "Support Operations Specialist",
    "Support Operations Analyst", "Triage Operations Specialist", "Incident Management Analyst",
    "Escalation Engineer", "Technical Escalations Specialist", "QA Engineer", "Software QA Engineer",
    "Software Test Engineer", "QA Analyst", "Senior QA Analyst", "QA Automation Engineer",
    "Test Automation Engineer", "Python QA Automation Engineer", "Quality Engineer — Software",
    "Product Quality Engineer — Software", "QA/Test Lead", "Data Quality Analyst", "Data Analyst",
    "Operations Data Analyst", "Business Data Analyst", "Reporting Analyst", "Process Improvement Analyst",
    "Process Improvement Specialist", "Business Process Analyst", "Technical Business Analyst",
    "Systems Analyst", "Operations Analyst", "Technical Program Coordinator", "Technical Project Coordinator",
    "Customer Success Engineer", "Technical Customer Success Specialist", "Implementation Consultant",
    "Implementation Specialist"
]

EXCLUDED_ROLES = [
    "Senior Software Engineer", "Backend Software Engineer", "Frontend Software Engineer",
    "Full-Stack Software Engineer", "Mobile Developer", "iOS Developer", "Android Developer",
    "DevOps Engineer", "Site Reliability Engineer (SRE)", "Cloud Infrastructure Engineer",
    "Platform Engineer", "Network Engineer", "Systems Administrator", "Cybersecurity Engineer",
    "Security Operations / SOC Analyst", "Penetration Tester", "Data Engineer",
    "Machine Learning Engineer", "AI/ML Engineer", "Data Scientist", "Research Scientist",
    "ML Research Engineer", "Database Administrator", "Solutions Architect", "Cloud Architect",
    "Enterprise Architect", "Senior Technical Architect", "Embedded Software Engineer",
    "Firmware Engineer", "Hardware Engineer", "Electronics Engineer", "Mechanical Engineer",
    "Manufacturing Quality Engineer", "Manufacturing QA / Quality Control Specialist",
    "Validation Engineer — Pharmaceutical/Medical Devices", "GMP Quality Specialist",
    "ISO Quality Manager", "Regulatory Affairs Specialist", "Clinical Quality Specialist",
    "Laboratory QA Analyst", "Construction QA/QC Engineer", "Civil Engineer", "Electrical Engineer",
    "Product Designer / UX Designer", "UI Designer", "Graphic Designer", "UX Researcher",
    "Product Manager", "Senior Program Manager", "Engineering Manager", "Software Development Manager",
    "Director of Engineering", "Head of QA / QA Director", "Enterprise Account Executive",
    "Sales Development Representative", "Technical Sales", "Financial Analyst", "Accountant",
    "Finance Manager", "HR Specialist", "Recruiter", "QA Lead"
]

TARGET_LOCATION = "Dublin, Ireland"
ACTIVE_SEARCHES: Dict[str, Dict[str, Any]] = {}
CV_PROFILE_CACHE: Dict[str, str] = {}
CV_ANALYSIS_CONCURRENCY = 2
SEARCH_LOG_LIMIT = 25
JOB_FIELDS = [
    "Job Title",
    "Company",
    "Location",
    "Posted Date",
    "Working Type",
    "Salary",
    "Fit Score (%)",
    "Match Reasons",
    "Job Description",
    "Recommended CV",
    "CV Tailoring Recommendation",
    "Status",
    "URL",
    "Listing Source",
    "Official Listing Verified",
    "Official Listing URL",
    "Original Listing URL",
    "URL Check Status",
    "User Dismissed",
    "Applied",
    "Verification Status",
    "Verification Notes",
    "Last Verified",
]
MIN_FULL_DESCRIPTION_LENGTH = 500


def is_expired_listing_text(text: str | None) -> bool:
    """Detect obsolete or closed listings that should be marked Expired."""
    if not text:
        return False
    normalized = text.lower()
    expired_markers = (
        "no longer accepting applications",
        "this job is no longer accepting applications",
        "applications are closed",
        "applications closed",
        "position is no longer open",
        "this role is no longer available",
        "job is no longer available",
        "this listing is no longer active",
        "expired listing",
        "application deadline has passed",
    )
    return any(marker in normalized for marker in expired_markers)


def normalize_job(job: Dict[str, Any]) -> Dict[str, Any] | None:
    """Keep only jobs with usable listing URLs and return the canonical CSV shape."""
    description = str(job.get("Job Description") or "").strip()
    if is_expired_listing_text(description):
        job["Status"] = "Expired"
        return None
    if (
        description.lower() in {"", "n/a", "not specified", "unknown"}
        or len(description) < MIN_FULL_DESCRIPTION_LENGTH
    ):
        return None

    source_url = str(job.get("Original Listing URL") or "").strip().strip("<>")
    official_url = str(job.get("Official Listing URL") or "").strip().strip("<>")
    submitted_url = str(job.get("URL") or "").strip().strip("<>")
    official_verified = str(job.get("Official Listing Verified") or "").strip().lower() == "yes"
    valid_url = lambda value: bool(re.match(r"^https?://[^\s]+$", value, re.IGNORECASE))

    if not valid_url(source_url):
        source_url = submitted_url if valid_url(submitted_url) else "Not specified"

    url = official_url if official_verified and valid_url(official_url) else source_url

    working_type = str(job.get("Working Type") or "Not specified").strip().lower()
    working_type_map = {
        "remote": "Remote",
        "hybrid": "Hybrid",
        "on-site": "On-site",
        "onsite": "On-site",
        "on site": "On-site",
    }

    return {
        field: str(job.get(field) or "Not specified").strip()
        for field in JOB_FIELDS
    } | {
        "URL": url,
        "Job Description": description,
        "Original Listing URL": source_url,
        "URL Check Status": "Not checked",
        "Working Type": working_type_map.get(working_type, "Not specified"),
    }


def _url_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2}


def _check_url_sync(url: str, job_title: str, company: str, allow_client_rendered: bool = False) -> bool:
    """Check HTTP reachability and listing identity without blocking the event loop."""
    headers = {"User-Agent": "CareerMatch/1.0 job-listing-check"}
    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=5) as response:
            if not 200 <= response.status < 400:
                return False
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                return True
            page = response.read(512_000).decode("utf-8", errors="ignore")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return False

    visible_text = re.sub(r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>|<[^>]+>", " ", page, flags=re.I | re.S)
    visible_text = unescape(re.sub(r"\s+", " ", visible_text)).lower()
    title_tokens = _url_tokens(job_title)
    company_tokens = _url_tokens(company)
    title_matches = sum(token in visible_text for token in title_tokens)
    company_matches = sum(token in visible_text for token in company_tokens)
    soft_404_markers = (
        "job no longer available",
        "this job is no longer available",
        "page not found",
        "no jobs found",
        "job does not exist",
    )
    url_text = unescape(url.lower().replace("-", " ").replace("_", " "))
    url_title_matches = sum(token in url_text for token in title_tokens)

    return (
        not any(marker in visible_text for marker in soft_404_markers)
        and (
            (
                title_matches >= max(1, min(3, len(title_tokens)))
                and company_matches >= 1
            )
            or (allow_client_rendered and url_title_matches >= max(1, min(3, len(title_tokens))))
        )
    )


async def validate_listing_job(job: Dict[str, Any]) -> Dict[str, Any] | None:
    """Prefer a reachable official URL but retain jobs with unavailable links."""
    source_url = job["Original Listing URL"]
    job_title = job.get("Job Title", "")
    company = job.get("Company", "")
    official_url = job.get("Official Listing URL", "Not specified")
    official_verified = str(job.get("Official Listing Verified", "")).lower() == "yes"

    source_reachable, official_reachable = await asyncio.gather(
        asyncio.to_thread(_check_url_sync, source_url, job_title, company)
        if source_url.startswith("http") else asyncio.sleep(0, result=False),
        asyncio.to_thread(_check_url_sync, official_url, job_title, company, True)
        if official_verified and official_url != "Not specified"
        else asyncio.sleep(0, result=False),
    )

    if official_reachable:
        job["URL"] = official_url
        job["URL Check Status"] = "Official listing reachable"
    elif source_reachable:
        job["URL"] = source_url
        job["Official Listing Verified"] = "No"
        job["Official Listing URL"] = "Not specified"
        job["URL Check Status"] = "Source listing reachable"
    else:
        job["URL Check Status"] = "URL unavailable or blocked; job retained"
        logger.warning(f"Retaining job with unavailable URL: {job.get('Job Title')} ({source_url})")

    return job


async def validate_listing_urls(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate all listing URLs concurrently and keep reachable jobs only."""
    checked_jobs = await asyncio.gather(*(validate_listing_job(job) for job in jobs))
    return [job for job in checked_jobs if job is not None]

def update_search_status(search_id: str, message: str, progress: int | None = None) -> None:
    """Track a running search so the frontend can show live progress updates."""
    status = ACTIVE_SEARCHES.setdefault(
        search_id,
        {"status": "running", "progress": 0, "message": message, "logs": []}
    )
    status["message"] = message
    if progress is not None:
        status["progress"] = progress
    status["logs"] = (status.get("logs") or []) + [message]
    if len(status["logs"]) > SEARCH_LOG_LIMIT:
        status["logs"] = status["logs"][-SEARCH_LOG_LIMIT:]
    logger.info(f"[search:{search_id}] {message}")


def parse_role_input(value: str | None, fallback: List[str]) -> List[str]:
    """Parse comma- or newline-separated roles and remove duplicate entries."""
    if not value or not value.strip():
        return fallback.copy()

    roles = [role.strip() for role in re.split(r"[,\n]", value) if role.strip()]
    return list(dict.fromkeys(roles)) or fallback.copy()


def update_verification_rows(rows: List[Dict[str, Any]]) -> None:
    """Merge verification results into the saved CSV by title and company."""
    jobs = import_jobs_from_csv("job_matches.csv")
    result_map = {
        (str(row.get("Job Title", "")).strip().lower(), str(row.get("Company", "").strip().lower())): row
        for row in rows
    }
    for job in jobs:
        key = (job.get("Job Title", "").strip().lower(), job.get("Company", "").strip().lower())
        result = result_map.get(key)
        if not result:
            continue

        verification_status = str(result.get("Verification Status") or "Not found").strip()
        verification_notes = str(result.get("Verification Notes") or "Not specified").strip()
        if is_expired_listing_text(verification_notes) or is_expired_listing_text(str(result.get("Official Listing URL") or "")):
            verification_status = "Expired"
        if is_expired_listing_text(str(result.get("Job Title") or "")) or is_expired_listing_text(str(result.get("Company") or "")):
            verification_status = "Expired"

        job["Verification Status"] = verification_status
        job["Verification Notes"] = verification_notes or "Not specified"
        job["Last Verified"] = date.today().isoformat()
        official_url = str(result.get("Official Listing URL") or "").strip()
        if official_url.startswith("http"):
            job["Official Listing URL"] = official_url
            job["Official Listing Verified"] = "Yes"
            job["URL"] = official_url
            job["Listing Source"] = "Official company website"
    from utils.csv_utils import export_jobs_to_csv
    export_jobs_to_csv(jobs, "job_matches.csv")


async def run_saved_job_verification(verification_id: str) -> None:
    """Check saved roles in AI batches and persist results after each batch."""
    try:
        jobs = import_jobs_from_csv("job_matches.csv")
        jobs = [job for job in jobs if job.get("User Dismissed", "").lower() != "yes"]
        batches = [jobs[index:index + 5] for index in range(0, len(jobs), 5)]
        for batch_index, batch in enumerate(batches, 1):
            progress = int(batch_index / max(1, len(batches)) * 90)
            update_search_status(verification_id, f"Verifying saved jobs batch {batch_index}/{len(batches)}...", progress)
            instructions = """
You verify saved job records using Google Search. Check the exact listing URL, then search the
employer's official careers website for the same exact title and location. Classify each as Active,
Expired, Blocked, or Not found. If the LinkedIn or employer page says "No longer accepting
applications", "applications are closed", "position is no longer open", or gives any similar closure
message, mark the job as Expired and do not treat it as an active listing. Never mark Active from a
generic careers homepage or a LinkedIn page that explicitly says applications are closed. Return ONLY a
JSON array with Job Title, Company, Verification Status, Verification Notes, and Official Listing URL.
"""
            prompt = "Verify these exact saved jobs:\n" + json.dumps([
                {"Job Title": job.get("Job Title"), "Company": job.get("Company"), "Location": job.get("Location"), "URL": job.get("URL"), "Original Listing URL": job.get("Original Listing URL")}
                for job in batch
            ], ensure_ascii=False)
            response = await call_gemini_with_retry(instructions, prompt, use_google_search=True, max_retries=3, initial_delay=5)
            try:
                verification_results = extract_json_array(response)
            except json.JSONDecodeError:
                update_search_status(verification_id, f"Batch {batch_index}: Gemini response was not JSON; trying OpenAI recovery...", progress)
                fallback_response = await call_openai_fallback(instructions, prompt, use_google_search=True)
                if not fallback_response:
                    raise
                verification_results = extract_json_array(fallback_response)
            update_verification_rows(verification_results)
            update_search_status(verification_id, f"Verified batch {batch_index}/{len(batches)} and saved results to CSV.", progress)
        ACTIVE_SEARCHES[verification_id]["status"] = "complete"
        ACTIVE_SEARCHES[verification_id]["progress"] = 100
        ACTIVE_SEARCHES[verification_id]["message"] = "Saved job verification complete."
    except Exception as exc:
        ACTIVE_SEARCHES[verification_id]["status"] = "error"
        ACTIVE_SEARCHES[verification_id]["error"] = str(exc)
        update_search_status(verification_id, f"Verification failed: {exc}", 0)

def extract_json_array(response: str) -> List[Dict[str, Any]]:
    """Extract the first valid JSON array from a model response."""
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\[", cleaned):
        try:
            parsed, _ = decoder.raw_decode(cleaned[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
            return parsed

    raise json.JSONDecodeError("No valid JSON job array found", cleaned, 0)


async def run_search_pipeline(
    search_id: str,
    files: List[tuple[str, bytes]],
    target_roles: List[str],
    excluded_roles: List[str],
    reuse_cv_analysis: bool,
) -> None:
    """Run the CV analysis + job search flow and save completion state for status polling."""
    try:
        total_files = len(files)
        analysis_semaphore = asyncio.Semaphore(CV_ANALYSIS_CONCURRENCY)

        async def process_cv(file_index: int, filename: str, content: bytes) -> tuple[str, str]:
            async with analysis_semaphore:
                content_hash = hashlib.sha256(content).hexdigest()
                update_search_status(
                    search_id,
                    f"Processing CV {file_index}/{total_files}: validating file...",
                    max(5, int((file_index - 1) / total_files * 35)),
                )
                validate_cv_filename(filename)
                cv_text = await extract_cv_text_from_bytes(filename, content)

                cv_summary = CV_PROFILE_CACHE.get(content_hash) if reuse_cv_analysis else None
                if cv_summary:
                    update_search_status(
                        search_id,
                        f"Reusing saved analysis for CV {file_index}/{total_files}...",
                        int(file_index / total_files * 35),
                    )
                else:
                    update_search_status(
                        search_id,
                        f"Analyzing CV {file_index}/{total_files} candidate profile...",
                        int(file_index / total_files * 35),
                    )
                    try:
                        cv_summary = await run_cv_analyzer_agent(cv_text)
                    except HTTPException as exc:
                        if exc.status_code != 503:
                            raise
                        cv_summary = (
                            "CV analysis was temporarily unavailable. Use the extracted CV content "
                            "directly for matching:\n" + cv_text[:12000]
                        )
                        update_search_status(
                            search_id,
                            f"CV {file_index}/{total_files} analysis unavailable; continuing with extracted CV text...",
                            int(file_index / total_files * 35),
                        )
                    CV_PROFILE_CACHE[content_hash] = cv_summary

                return filename, cv_summary

        analyzed_cvs = await asyncio.gather(
            *(process_cv(file_index, filename, content) for file_index, (filename, content) in enumerate(files, 1))
        )
        cv_summaries = [
            f"CV filename: {filename}\nCandidate profile:\n{cv_summary}"
            for filename, cv_summary in analyzed_cvs
        ]

        combined_summary = "\n\n--- NEXT CV PROFILE ---\n\n".join(cv_summaries)
        update_search_status(search_id, "Searching live jobs in batches...", 55)
        matched_jobs = await run_incremental_job_finder(
            combined_summary,
            search_id=search_id,
            target_roles=target_roles,
            excluded_roles=excluded_roles,
            cv_names=[filename for filename, _ in files],
        )

        if not matched_jobs:
            existing_jobs = import_jobs_from_csv("job_matches.csv")
            if existing_jobs:
                matched_jobs = existing_jobs
                update_search_status(search_id, f"Keeping {len(existing_jobs)} previous valid matches...", 72)
            else:
                matched_jobs = []
                update_search_status(search_id, "No matching jobs were found in this search.", 72)

        if matched_jobs:
            update_search_status(search_id, f"Persisting {len(matched_jobs)} matches to CSV...", 82)
            append_jobs_to_csv(matched_jobs, "job_matches.csv")
        else:
            update_search_status(search_id, "Skipping CSV write because no valid jobs were returned.", 82)

        update_search_status(search_id, "Exporting workbook to Excel...", 90)
        df = pd.DataFrame(matched_jobs)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Job Matches', index=False)
        output.seek(0)

        ACTIVE_SEARCHES[search_id]["status"] = "complete"
        ACTIVE_SEARCHES[search_id]["progress"] = 100
        ACTIVE_SEARCHES[search_id]["message"] = "Search complete. Excel file ready."
        ACTIVE_SEARCHES[search_id]["excel_bytes"] = output.getvalue()
        ACTIVE_SEARCHES[search_id]["filename"] = "job_matches.xlsx"
        ACTIVE_SEARCHES[search_id]["logs"] = (ACTIVE_SEARCHES[search_id].get("logs") or []) + ["Search complete. Excel file ready."]
        if len(ACTIVE_SEARCHES[search_id]["logs"]) > SEARCH_LOG_LIMIT:
            ACTIVE_SEARCHES[search_id]["logs"] = ACTIVE_SEARCHES[search_id]["logs"][-SEARCH_LOG_LIMIT:]
        logger.info(f"[search:{search_id}] Excel workbook generated successfully")

    except HTTPException as exc:
        ACTIVE_SEARCHES[search_id]["status"] = "error"
        ACTIVE_SEARCHES[search_id]["progress"] = 0
        ACTIVE_SEARCHES[search_id]["message"] = exc.detail
        ACTIVE_SEARCHES[search_id]["error"] = exc.detail
        update_search_status(search_id, f"Search failed: {exc.detail}", 0)
    except Exception as exc:  # pragma: no cover - defensive fallback
        ACTIVE_SEARCHES[search_id]["status"] = "error"
        ACTIVE_SEARCHES[search_id]["progress"] = 0
        ACTIVE_SEARCHES[search_id]["message"] = str(exc)
        ACTIVE_SEARCHES[search_id]["error"] = str(exc)
        update_search_status(search_id, f"Unexpected error: {exc}", 0)


async def call_gemini_with_retry(
    instructions: str,
    prompt: str,
    use_google_search: bool = False,
    max_retries: int = 5,
    initial_delay: int = 8
) -> str:
    """
    Calls Gemini API with retry logic for temporary spikes.

    When live web-search is required, this uses the Google GenAI SDK directly so the
    `google_search` tool is actually enabled for the request. The previous CrewAI 
    path ignored the `use_google_search` flag and therefore produced no live job data.
    """
    delay = initial_delay
    openai_attempted = False
    openai_error = ""

    def run_gemini_request() -> Any:
        from google import genai

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise HTTPException(status_code=401, detail="Missing GOOGLE_API_KEY")

        client = genai.Client(api_key=api_key)
        return client.models.generate_content(
            model="gemini-flash-latest",
            contents=f"{instructions}\n\n{prompt}",
            config={"tools": [{"google_search": {}}]} if use_google_search else None,
        )

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Calling Gemini (attempt {attempt}/{max_retries})...")

            if use_google_search:
                response = await asyncio.wait_for(
                    asyncio.to_thread(run_gemini_request),
                    timeout=120,
                )

                text = getattr(response, "text", None)
                if text:
                    return str(text)

                candidates = getattr(response, "candidates", None) or []
                for candidate in candidates:
                    content = getattr(candidate, "content", None)
                    if not content:
                        continue
                    parts = getattr(content, "parts", []) or []
                    for part in parts:
                        part_text = getattr(part, "text", None)
                        if part_text:
                            return str(part_text)

                raise ValueError("Gemini returned an empty response for a Google Search call")

            response = await asyncio.wait_for(
                asyncio.to_thread(run_gemini_request),
                timeout=120,
            )
            text = getattr(response, "text", None)
            if text:
                return str(text)

            raise ValueError("Gemini returned an empty response for CV analysis")

        except Exception as e:
            err_str = str(e)
            if isinstance(e, asyncio.TimeoutError):
                err_str = "Google Search request timed out after 120 seconds"

            if attempt == 1 and os.getenv("OPENAI_API_KEY"):
                openai_attempted = True
                logger.warning("Gemini failed on the first attempt; OpenAI fallback started")
                openai_result = await call_openai_fallback(instructions, prompt, use_google_search)
                if openai_result is not None:
                    return openai_result
                openai_error = "OpenAI fallback failed or returned no usable response"
                raise HTTPException(
                    status_code=503,
                    detail=f"Gemini failed once; OpenAI fallback also failed: {openai_error}"
                )

            is_transient = any(
                code in err_str
                for code in ["503", "500", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"]
            )

            if is_transient and attempt < max_retries:
                logger.warning(
                    f"⚠️ Server busy ({err_str[:60]}...). "
                    f"Retrying in {delay}s (Attempt {attempt}/{max_retries})..."
                )
                await asyncio.sleep(delay)
                delay *= 2
            else:
                logger.error(f"Gemini API call failed: {e}")
                fallback_detail = f"; {openai_error}" if openai_attempted else "; OpenAI fallback was not configured"
                raise HTTPException(
                    status_code=503,
                    detail=f"Gemini request failed after {attempt} attempt(s): {type(e).__name__}: {err_str[:240]}{fallback_detail}"
                )


async def call_openai_fallback(
    instructions: str,
    prompt: str,
    use_google_search: bool,
) -> str | None:
    """Use OpenAI only when configured and Gemini has exhausted its retries."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    def run_openai_request() -> Any:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        request: Dict[str, Any] = {
            "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            "input": f"{instructions}\n\n{prompt}",
        }
        if use_google_search:
            request["tools"] = [{"type": "web_search_preview"}]
        return client.responses.create(**request)

    try:
        logger.warning("Gemini unavailable; trying OpenAI fallback...")
        response = await asyncio.wait_for(
            asyncio.to_thread(run_openai_request),
            timeout=120,
        )
        text = getattr(response, "output_text", None)
        if text:
            logger.info("OpenAI fallback completed successfully")
            return str(text)
        raise ValueError("OpenAI returned an empty response")
    except Exception as exc:
        logger.error(f"OpenAI fallback failed: {type(exc).__name__}: {exc}")
        return None


async def run_cv_analyzer_agent(cv_text: str) -> str:
    """
    AGENT 1: Analyzes CV and builds a detailed candidate profile.
    
    Args:
        cv_text: Extracted text from the CV
        
    Returns:
        Candidate profile summary
    """
    logger.info("🤖 Agent 1 (CV Analyzer) starting - analyzing candidate profile...")
    
    instructions = f"""
    You are an expert technical recruiter matching candidates for roles in {TARGET_LOCATION}.
    
    Analyze the provided resume and synthesize a detailed candidate profile:
    1. Core technical skills & primary tech stack
    2. Seniority level & total years of experience
    3. Key strengths and specializations (e.g., QA testing, AI operations, triage)
    4. Target role keywords that align with the candidate
    
    Be specific and detailed to help with job matching accuracy.
    """
    
    prompt = f"Analyze this CV and create a detailed candidate profile for {TARGET_LOCATION} job matching:\n\n{cv_text}"
    
    response = await call_gemini_with_retry(
        instructions,
        prompt,
        use_google_search=False,
        max_retries=2,
        initial_delay=3,
    )
    logger.info("✅ Agent 1 completed: Candidate profile created")
    return response


async def run_incremental_job_finder(
    cv_summary: str,
    search_id: str | None = None,
    target_roles: List[str] | None = None,
    excluded_roles: List[str] | None = None,
    cv_names: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """
    AGENT 2: Searches for jobs in batches using Google Search and matches to candidate.
    
    Args:
        cv_summary: Candidate profile from Agent 1
        search_id: Optional active search ID for live progress updates
        
    Returns:
        List of matched job opportunities
    """
    target_roles = target_roles or TARGET_ROLES
    excluded_roles = excluded_roles or EXCLUDED_ROLES
    cv_names = cv_names or ["Uploaded CV"]
    logger.info(f"🤖 Agent 2 (Job Finder) starting - batching {len(target_roles)} target roles...")
    
    # Match the notebook approach: work in smaller role batches so partial results
    # are preserved and transient Gemini 503s do not block all earlier progress.
    batch_size = 5
    roles_batches = [target_roles[i:i + batch_size] for i in range(0, len(target_roles), batch_size)]
    excluded_str = ", ".join(excluded_roles)
    
    all_jobs = []
    
    for batch_idx, role_batch in enumerate(roles_batches, 1):
        batch_roles_str = ", ".join(role_batch)
        logger.info(
            f"🔍 [Batch {batch_idx}/{len(roles_batches)}] "
            f"Searching for roles: {batch_roles_str[:80]}..."
        )
        if search_id:
            progress_pct = 55 + int((batch_idx / len(roles_batches)) * 35)
            update_search_status(
                search_id,
                f"Searching batch {batch_idx}/{len(roles_batches)}: {batch_roles_str[:80]}...",
                progress_pct,
            )
            update_search_status(
                search_id,
                f"Waiting for Gemini and Google Search results for batch {batch_idx}/{len(roles_batches)}...",
                progress_pct,
            )
        
        instructions = f"""
        You are an automated career matching agent using Google Search.
        
        Search for ACTIVE open job listings specifically in **{TARGET_LOCATION}** matching:
        [{batch_roles_str}]
        
        STRICT EXCLUSION LIST (DO NOT INCLUDE ANY OF THESE ROLES):
        [{excluded_str}]
        
        CRITICAL REQUIREMENTS:
        1. Only return jobs posted within the last 7 days
        2. Filter out any jobs older than 1 week
          3. If the listing page says "No longer accepting applications", "applications are closed",
              "position is no longer open", "role is no longer active", or any equivalent closure note,
              treat it as Expired and do not save it as an active job. Ignore these listings entirely.
        4. Match candidate skills from profile: {cv_summary[:300]}...
          5. Return the exact direct URL of each job listing from the search result; never use N/A,
              a company homepage, a search page, or a fabricated URL. If no direct listing URL is
              available, include the job with "Not specified" and mark the URL status accordingly.
          6. Extract the posting date when visible. Use "Not specified" only when the listing does
              not show a date. Normalize working type to exactly Remote, Hybrid, On-site, or
              Not specified.
          6a. Extract the salary or compensation exactly as shown. Use "Not specified" when it is
              not available; do not estimate or invent salary.
          7. Select the best matching CV filename from this list and return it exactly:
              [{", ".join(cv_names)}]
          8. Provide a concrete recommendation for tailoring that selected CV to this job,
              including which skills, experience, or keywords to emphasize.
          9. Extract the complete job description from the original listing, preserving all
              available sections, paragraphs, responsibilities, requirements, qualifications,
              benefits, and other visible content. Do not summarize or shorten it. Do not invent
              details. The description must contain at least 500 characters of source text. If the
              full description cannot be retrieved, do not return that job.
          10. Search across Google results from LinkedIn, Indeed, IrishJobs, Greenhouse,
               company career sites, and other relevant job boards. If the result comes from
               LinkedIn, Indeed, IrishJobs, or another job board, search the employer's official
               careers domain for the same role and location. Prefer the official employer listing
               URL in the URL field when it exists. Do not treat a company careers homepage, a
               generic Greenhouse board, or a different job ID as verification. The official page
               must show the exact job title and employer; otherwise mark it No.
          11. Set Listing Source to Official company website or the job-board name. Set Official
              Listing Verified to Yes only when the exact role is found on the official employer
              site; otherwise set it to No and put Not specified in Official Listing URL.
          12. Always return Original Listing URL as the exact direct URL where the job was found.
              Return the official URL in URL when verified; otherwise return the original job-board
              URL in URL.
        
        Output ONLY a valid JSON array (no markdown, no ```json wrapper):
        [
          {{
            "Job Title": "Exact Job Title",
            "Company": "Company Name",
            "Location": "Location",
            "Fit Score (%)": "e.g., 85%",
            "Job Description": "Complete job description copied verbatim from the original listing",
            "Recommended CV": "Exact uploaded CV filename",
            "CV Tailoring Recommendation": "Specific changes or emphasis for this job",
            "Status": "Active",
                        "URL": "https://direct-job-listing-url",
                        "Listing Source": "Official company website or job board name",
                        "Official Listing Verified": "Yes or No",
                        "Official Listing URL": "https://official-exact-job-listing or Not specified",
                        "Original Listing URL": "https://exact-source-job-listing",
                        "Posted Date": "YYYY-MM-DD or Not specified",
                        "Working Type": "Remote, Hybrid, On-site, or Not specified"
                        ,"Salary": "Salary or compensation exactly as listed, or Not specified"
          }}
        ]
        """
        
        prompt = (
            f"Search Google for job listings in {TARGET_LOCATION} "
            f"for these roles: {batch_roles_str}. "
            f"Only include jobs posted in the last 7 days. "
            f"Match them against this candidate profile:\n{cv_summary}"
        )
        
        try:
            response = await call_gemini_with_retry(
                instructions,
                prompt,
                use_google_search=True,
                max_retries=5,
                initial_delay=8
            )

            # Parse JSON response
            try:
                batch_jobs = extract_json_array(response)
                if isinstance(batch_jobs, list):
                    valid_jobs = [normalize_job(job) for job in batch_jobs if isinstance(job, dict)]
                    valid_jobs = [job for job in valid_jobs if job is not None]
                    valid_jobs = await validate_listing_urls(valid_jobs)
                    all_jobs.extend(valid_jobs)
                    if len(valid_jobs) > 0:
                        append_jobs_to_csv(valid_jobs, "job_matches.csv")
                        result_message = f"Batch {batch_idx}: found {len(valid_jobs)} jobs and saved them to CSV."
                        logger.info(f"✅ {result_message}")
                    else:
                        result_message = f"Batch {batch_idx}: no valid jobs returned by the AI response."
                        logger.info(f"ℹ️ {result_message}")

                    if search_id:
                        update_search_status(search_id, result_message, progress_pct)
                else:
                    result_message = f"Batch {batch_idx}: no valid jobs returned."
                    logger.warning(f"⚠️ {result_message}")
                    if search_id:
                        update_search_status(search_id, result_message, progress_pct)
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ Batch {batch_idx}: Gemini returned invalid JSON; trying OpenAI recovery...")
                recovered_jobs: List[Dict[str, Any]] = []
                openai_response = await call_openai_fallback(instructions, prompt, use_google_search=True)
                if openai_response:
                    try:
                        recovered_jobs = [
                            job for job in extract_json_array(openai_response)
                            if isinstance(job, dict)
                        ]
                    except json.JSONDecodeError:
                        recovered_jobs = []

                valid_jobs = [normalize_job(job) for job in recovered_jobs]
                valid_jobs = [job for job in valid_jobs if job is not None]
                valid_jobs = await validate_listing_urls(valid_jobs)
                all_jobs.extend(valid_jobs)
                if valid_jobs:
                    append_jobs_to_csv(valid_jobs, "job_matches.csv")
                    result_message = f"Batch {batch_idx}: recovered {len(valid_jobs)} jobs with OpenAI and saved them to CSV."
                else:
                    result_message = f"Batch {batch_idx}: both AI responses were not parseable; no jobs parsed."
                logger.warning(f"⚠️ {result_message} - {e}")
                if search_id:
                    update_search_status(search_id, result_message, progress_pct)
                continue

            # Small delay only to avoid rate limiting.
            if batch_idx < len(roles_batches):
                await asyncio.sleep(1)

        except HTTPException as e:
            if "503" in str(e.detail) or "rate" in str(e.detail).lower():
                if all_jobs:
                    result_message = (
                        f"Search interrupted after batch {batch_idx}: {len(all_jobs)} jobs found so far. "
                        "Partial results will be kept."
                    )
                    logger.info(f"🛑 {result_message}")
                    if search_id:
                        update_search_status(search_id, result_message, progress_pct)
                else:
                    result_message = (
                        f"Search interrupted after batch {batch_idx}: no jobs found before the error."
                    )
                    logger.info(f"🛑 {result_message}")
                    if search_id:
                        update_search_status(search_id, result_message, progress_pct)
                break
            else:
                result_message = f"Batch {batch_idx} failed: {e.detail}. Continuing..."
                logger.warning(f"⚠️ {result_message}")
                if search_id:
                    update_search_status(search_id, result_message, progress_pct)
                continue
    
    if all_jobs:
        logger.info(f"✅ Agent 2 complete with partial results: Found {len(all_jobs)} total matching jobs")
    else:
        logger.info("✅ Agent 2 complete: No jobs found before the search ended")
    return all_jobs


def validate_cv_filename(filename: str | None) -> None:
    """Validate the filename of an uploaded CV file."""
    if not filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    filename_lower = filename.lower()
    if not filename_lower.endswith(('.pdf', '.docx')):
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported"
        )

    logger.info(f"File {filename} passed validation checks")


async def extract_cv_text_from_bytes(filename: str, content: bytes) -> str:
    """Extract text from a PDF or DOCX payload without needing the UploadFile object."""
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    filename_lower = filename.lower()

    if filename_lower.endswith('.pdf'):
        try:
            pdf = PdfReader(io.BytesIO(content))
            if not pdf.pages:
                raise HTTPException(status_code=422, detail="PDF has no pages")

            cv_text = ""
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    cv_text += text
                    logger.debug(f"Extracted {len(text)} chars from PDF page {page_num}")

            if not cv_text.strip():
                logger.warning("PDF extracted but contains no readable text")
                raise HTTPException(status_code=422, detail="PDF contains no readable text")

            logger.info(f"Successfully extracted {len(cv_text)} chars from PDF")
            return cv_text

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"PDF parsing failed: {type(e).__name__}: {e}")
            raise HTTPException(status_code=422, detail="Invalid or corrupted PDF file")

    elif filename_lower.endswith('.docx'):
        try:
            doc = Document(io.BytesIO(content))
            if not doc.paragraphs:
                raise HTTPException(status_code=422, detail="DOCX has no content")

            cv_text = ""
            for para in doc.paragraphs:
                if para.text.strip():
                    cv_text += para.text + "\n"
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            cv_text += cell.text + " "
                    cv_text += "\n"

            if not cv_text.strip():
                logger.warning("DOCX extracted but contains no readable text")
                raise HTTPException(status_code=422, detail="DOCX contains no readable text")

            logger.info(f"Successfully extracted {len(cv_text)} chars from DOCX")
            return cv_text

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"DOCX parsing failed: {type(e).__name__}: {e}")
            raise HTTPException(status_code=422, detail="Invalid or corrupted DOCX file")

    raise HTTPException(status_code=400, detail="Unsupported file type")


@app.post("/api/search/start")
async def start_search(
    files: List[UploadFile] = File(default=[]),
    file: UploadFile | None = File(default=None),
    target_roles: str | None = Form(default=None),
    excluded_roles: str | None = Form(default=None),
    reuse_cv_analysis: bool = Form(default=True),
) -> JSONResponse:
    """Start a background job search and return a live search ID for polling."""
    uploaded_files = list(files)
    if file is not None:
        uploaded_files.append(file)
    if not uploaded_files:
        raise HTTPException(status_code=400, detail="Upload at least one PDF or DOCX CV file")

    file_payloads = [(uploaded_file.filename or "unknown.pdf", await uploaded_file.read()) for uploaded_file in uploaded_files]
    parsed_target_roles = parse_role_input(target_roles, TARGET_ROLES)
    parsed_excluded_roles = parse_role_input(excluded_roles, EXCLUDED_ROLES)
    search_id = f"search-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    ACTIVE_SEARCHES[search_id] = {
        "status": "queued",
        "progress": 0,
        "message": "Starting job search...",
        "logs": ["Starting job search..."],
        "total_files": len(file_payloads),
        "reuse_cv_analysis": reuse_cv_analysis,
    }
    asyncio.create_task(run_search_pipeline(
        search_id,
        file_payloads,
        parsed_target_roles,
        parsed_excluded_roles,
        reuse_cv_analysis,
    ))
    return JSONResponse({
        "search_id": search_id,
        "status": "queued",
        "message": f"Search started for {len(file_payloads)} CV(s)",
    })


@app.get("/api/search/status/{search_id}")
async def get_search_status(search_id: str) -> JSONResponse:
    """Return the current progress and log stream for an active search."""
    status = ACTIVE_SEARCHES.get(search_id)
    if not status:
        raise HTTPException(status_code=404, detail="Search not found")

    return JSONResponse(
        {
            "search_id": search_id,
            "status": status.get("status", "running"),
            "progress": status.get("progress", 0),
            "message": status.get("message", "Processing..."),
            "logs": status.get("logs", []),
            "download_url": f"/api/search/result/{search_id}" if status.get("status") == "complete" else None,
            "error": status.get("error"),
        }
    )


@app.get("/api/search/result/{search_id}")
async def get_search_result(search_id: str) -> StreamingResponse:
    """Download the Excel workbook for a completed search."""
    status = ACTIVE_SEARCHES.get(search_id)
    if not status or status.get("status") != "complete":
        raise HTTPException(status_code=404, detail="Search not complete")

    excel_bytes = status.get("excel_bytes")
    if not excel_bytes:
        raise HTTPException(status_code=404, detail="Excel file not available")

    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={status.get('filename', 'job_matches.xlsx')}"}
    )


@app.get("/api/jobs")
async def get_jobs() -> JSONResponse:
    """
    Fetch all jobs from CSV file.
    
    Returns:
        JSON array of job objects
    """
    try:
        jobs = import_jobs_from_csv("job_matches.csv")
        jobs = [job for job in jobs if job.get("User Dismissed", "").lower() != "yes"]
        
        if not jobs:
            return JSONResponse(
                status_code=200,
                content={"jobs": [], "message": "No jobs found. Upload a CV to search."}
            )
        
        logger.info(f"✅ Fetched {len(jobs)} jobs from CSV")
        return JSONResponse(
            status_code=200,
            content={"jobs": jobs, "total": len(jobs)}
        )

    except Exception as e:
        logger.error(f"Error fetching jobs: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch jobs from database"
        )


@app.post("/api/jobs/dismiss")
async def dismiss_job(
    job_title: str = Form(...),
    company: str = Form(...),
) -> JSONResponse:
    """Hide a job from the listing while retaining it in CSV for deduplication."""
    dismissed = dismiss_job_in_csv(job_title, company, "job_matches.csv")
    if not dismissed:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse({"dismissed": True, "message": "Job dismissed and retained in CSV"})


@app.post("/api/jobs/update-url")
async def update_job_url(
    job_title: str = Form(...),
    company: str = Form(...),
    url: str = Form(...),
) -> JSONResponse:
    """Save a user-confirmed preferred listing URL for a job."""
    if not re.match(r"^https?://[^\s]+$", url.strip(), re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Enter a valid http(s) URL")
    updated = update_job_url_in_csv(job_title, company, url.strip(), "job_matches.csv")
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse({"updated": True, "url": url.strip()})


@app.post("/api/jobs/applied")
async def update_job_applied(
    job_title: str = Form(...),
    company: str = Form(...),
    applied: bool = Form(...),
) -> JSONResponse:
    """Persist the user's applied/not-applied status for a job."""
    updated = update_job_applied_in_csv(job_title, company, applied, "job_matches.csv")
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse({"updated": True, "applied": applied})


@app.post("/api/jobs/status")
async def update_job_status(
    job_title: str = Form(...),
    company: str = Form(...),
    status: str = Form(...),
) -> JSONResponse:
    """Persist a manual verification status for a job row."""
    if not status.strip():
        raise HTTPException(status_code=400, detail="Status is required")

    updated = update_job_status_in_csv(job_title, company, status.strip(), "job_matches.csv")
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse({"updated": True, "status": status.strip()})


@app.post("/api/jobs/verify/start")
async def start_job_verification() -> JSONResponse:
    """Start AI verification of the saved job listings."""
    verification_id = f"verify-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    ACTIVE_SEARCHES[verification_id] = {
        "status": "queued",
        "progress": 0,
        "message": "Starting saved job verification...",
        "logs": ["Starting saved job verification..."],
    }
    asyncio.create_task(run_saved_job_verification(verification_id))
    return JSONResponse({"verification_id": verification_id, "status": "queued"})

