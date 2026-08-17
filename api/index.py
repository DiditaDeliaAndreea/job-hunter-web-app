import asyncio
from collections import Counter
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

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pypdf import PdfReader
from docx import Document
from google.api_core.exceptions import NotFound as GoogleNotFound
from openpyxl import Workbook

# Import CSV utilities
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.csv_utils import append_jobs_to_csv, dismiss_expired_jobs_in_csv, dismiss_job_in_csv, import_jobs_from_csv, import_local_jobs_from_csv, update_job_applied_in_csv, update_job_status_in_csv, update_job_url_in_csv
from utils import firebase_utils

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load local environment variables (.env)
load_dotenv()


def get_current_user(authorization: str | None = Header(default=None)) -> Dict[str, Any]:
    """Verify a Firebase ID token supplied by the browser."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in is required")
    try:
        return firebase_utils.verify_id_token(authorization[7:].strip())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Firebase server credentials are not configured") from exc
    except Exception as exc:
        logger.warning("Firebase token verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired sign-in session") from exc


def get_prompt_learning_context(user_id: str) -> str:
    preferences = firebase_utils.fetch_prompt_preferences(user_id)
    if not preferences:
        return "No saved tailoring preferences yet."
    return "\n".join(
        f"- Previous user preference ({record.get('interaction_type', 'tailor')}): {record.get('prompt', '')}"
        for record in preferences
        if str(record.get("prompt", "")).strip()
    )

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


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({"service": "CareerMatch API", "status": "ok"})


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})

# Add CORS middleware to allow requests from frontend
frontend_urls = [
    origin.strip().rstrip("/")
    for origin in os.getenv("FRONTEND_URL", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(frontend_urls + ["http://localhost:3000", "http://localhost:8000"])),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# TARGET AND EXCLUDED ROLES CONFIGURATION
# ============================================================================

TARGET_ROLES = []

EXCLUDED_ROLES = []

TARGET_LOCATION = ""
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
    "Missing Requirements",
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
    "User Status Override",
    "Verification Status",
    "Verification Notes",
    "Last Verified",
]


def _size_bucket(size: int) -> str:
    if size <= 1 * 1024 * 1024:
        return "0-1MB"
    if size <= 5 * 1024 * 1024:
        return "1-5MB"
    if size <= 10 * 1024 * 1024:
        return "5-10MB"
    return "over-10MB"


def _text_bucket(length: int) -> str:
    if length < 100:
        return "0-99"
    if length < 1000:
        return "100-999"
    if length < 5000:
        return "1000-4999"
    return "5000+"


def _file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix[1:] if suffix in {".pdf", ".docx"} else "other"


def _diagnostic_error_code(detail: object) -> str:
    message = str(detail).lower()
    if "scanned or image-only" in message or "no readable" in message or "selectable text" in message:
        return "no_extractable_text"
    if "corrupted" in message or "invalid" in message:
        return "invalid_file"
    if "rate" in message or "503" in message or "temporarily unavailable" in message:
        return "provider_unavailable"
    if "timeout" in message:
        return "timeout"
    return "internal_error"


def record_diagnostic_event(user_id: str, event: str, details: Dict[str, Any] | None = None) -> None:
    """Persist allowlisted operational data without user content."""
    if not firebase_utils.is_configured():
        return
    try:
        firebase_utils.save_diagnostic_log(user_id, event, details or {})
    except Exception as exc:  # Diagnostics must never break the user request.
        logger.warning("Could not persist diagnostic event %s: %s", event, type(exc).__name__)


def is_diagnostics_admin(user_id: str) -> bool:
    configured_admins = {
        value.strip()
        for value in os.getenv("ADMIN_UIDS", "").split(",")
        if value.strip()
    }
    return user_id in configured_admins
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


def _url_is_expired_sync(url: str) -> bool:
    """Detect definitive HTTP removal or closure text for a saved listing URL."""
    if not url.startswith("http"):
        return False

    headers = {"User-Agent": "CareerMatch/1.0 job-listing-check"}
    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                return False
            page = response.read(512_000).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        return exc.code in {404, 410}
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False

    visible_text = re.sub(r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>|<[^>]+>", " ", page, flags=re.I | re.S)
    visible_text = unescape(re.sub(r"\s+", " ", visible_text))
    return is_expired_listing_text(visible_text)


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
        "no longer accepting applications",
        "this job is no longer accepting applications",
        "applications are closed",
        "applications closed",
        "position is no longer open",
        "this role is no longer available",
        "job is no longer available",
        "this listing is no longer active",
        "application deadline has passed",
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

    source_expired, source_reachable, official_reachable = await asyncio.gather(
        asyncio.to_thread(_url_is_expired_sync, source_url)
        if source_url.startswith("http") else asyncio.sleep(0, result=False),
        asyncio.to_thread(_check_url_sync, source_url, job_title, company)
        if source_url.startswith("http") else asyncio.sleep(0, result=False),
        asyncio.to_thread(_check_url_sync, official_url, job_title, company, True)
        if official_verified and official_url != "Not specified"
        else asyncio.sleep(0, result=False),
    )

    if source_expired:
        logger.info(f"Dropping expired listing: {job_title} at {company} ({source_url})")
        return None

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


def _normalize_search_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


ROLE_VARIANT_MAP = {
    "qa": ["QA Engineer", "Quality Assurance Engineer", "Software QA Engineer", "Software Test Engineer", "QA Analyst", "QA Automation Engineer", "Test Automation Engineer", "Quality Engineer"],
    "quality assurance": ["QA Engineer", "Quality Assurance Engineer", "Software QA Engineer", "QA Analyst", "Quality Engineer", "Software Test Engineer"],
    "support engineer": ["Technical Support Engineer", "Support Engineer", "Customer Support Engineer", "Application Support Engineer", "Technical Support Specialist", "Product Support Engineer", "Customer Experience Engineer"],
    "technical support": ["Technical Support Engineer", "Technical Support Specialist", "Application Support Engineer", "Customer Support Engineer", "Product Support Engineer"],
    "incident": ["Incident Response Analyst", "Incident Management Analyst", "Technical Support Engineer", "Operations Analyst", "Incident Analyst"],
    "operations analyst": ["Operations Analyst", "Operations Data Analyst", "Support Operations Analyst", "Technical Operations Analyst", "Business Operations Analyst"],
    "analyst": ["Analyst", "Operations Analyst", "Data Analyst", "Business Analyst", "Systems Analyst", "Technical Analyst", "Reporting Analyst", "Quality Analyst"],
    "customer success": ["Customer Success Engineer", "Technical Customer Success Specialist", "Implementation Consultant", "Implementation Specialist", "Customer Success Specialist"],
    "implementation": ["Implementation Consultant", "Implementation Specialist", "Technical Consultant", "Solutions Consultant"],
    "consultant": ["Technical Consultant", "Solutions Consultant", "Implementation Consultant", "Technical Solutions Consultant", "Customer Solutions Engineer"],
    "systems analyst": ["Systems Analyst", "Business Systems Analyst", "Technical Business Analyst", "Operations Analyst", "Product Operations Analyst"],
    "quality analyst": ["QA Analyst", "Quality Analyst", "Data Quality Analyst", "AI Quality Analyst", "Quality Assurance Analyst"],
    "test engineer": ["Software Test Engineer", "Test Automation Engineer", "QA Engineer", "Quality Assurance Engineer", "Software QA Engineer"],
    "ai support": ["AI Support Specialist", "AI Support Engineer", "AI Operations Analyst", "AI Operations Specialist", "Generative AI Support Specialist"],
    "product support": ["Product Support Engineer", "Product Support Specialist", "Customer Support Engineer", "Technical Support Engineer"],
}


def _expand_role_variants(role: str) -> List[str]:
    cleaned = _normalize_search_value(role)
    if not cleaned:
        return []
    variants = {cleaned}
    lower = cleaned.casefold()
    for key, values in ROLE_VARIANT_MAP.items():
        if key in lower or lower in key:
            variants.update(value for value in values if value.strip())
    replacements = [
        ("quality assurance engineer", "QA Engineer"),
        ("quality engineer", "QA Engineer"),
        ("software quality assurance engineer", "Software QA Engineer"),
        ("technical support specialist", "Technical Support Engineer"),
        ("support specialist", "Technical Support Engineer"),
        ("incident response specialist", "Incident Response Analyst"),
        ("incident management specialist", "Incident Management Analyst"),
    ]
    for source, replacement in replacements:
        if lower == source:
            variants.add(replacement)
    return [value for value in dict.fromkeys(variants) if value.strip()]


def extract_cv_role_suggestions(cv_summary: str) -> List[str]:
    """Read structured role suggestions from the CV analyzer response."""
    text = str(cv_summary or "").strip()
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        parsed = {}

    if isinstance(parsed, dict):
        role_candidates = parsed.get("matching_roles") or parsed.get("target_roles") or parsed.get("role_matches") or []
        if isinstance(role_candidates, list):
            roles = [
                _normalize_search_value(str(role))
                for role in role_candidates
                if str(role).strip()
            ]
            if roles:
                return roles

    matches = re.findall(r"(?:\b(?:QA|Quality Assurance|Technical Support|Customer Support|Application Support|Product Support|Systems Analyst|Operations Analyst|Incident Response|Incident Management|Customer Success|Implementation|Support|Software Quality|Test Automation|Quality Analyst|Data Analyst|Business Analyst)\b[^\n]{0,80})", text, flags=re.IGNORECASE)
    roles = []
    for match in matches:
        cleaned = _normalize_search_value(match)
        if cleaned and cleaned not in roles:
            roles.append(cleaned)
    return roles[:12]


def extract_cv_languages(cv_summary: str) -> List[str]:
    """Extract spoken-language signals from a CV summary or analyzer JSON."""
    text = str(cv_summary or "").strip()
    language_aliases = {
        "english": "English",
        "irish": "Irish",
        "romanian": "Romanian",
        "french": "French",
        "spanish": "Spanish",
        "german": "German",
        "italian": "Italian",
        "portuguese": "Portuguese",
        "dutch": "Dutch",
        "arabic": "Arabic",
        "chinese": "Chinese",
        "japanese": "Japanese",
        "korean": "Korean",
        "polish": "Polish",
        "czech": "Czech",
        "greek": "Greek",
        "russian": "Russian",
        "ukrainian": "Ukrainian",
        "hungarian": "Hungarian",
        "swedish": "Swedish",
        "norwegian": "Norwegian",
        "danish": "Danish",
        "finnish": "Finnish",
        "turkish": "Turkish",
        "latvian": "Latvian",
        "lithuanian": "Lithuanian",
        "slovak": "Slovak",
    }

    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        parsed = {}

    if isinstance(parsed, dict):
        for key in ["languages", "language_skills", "spoken_languages", "spoken_language_skills", "linguistic_skills"]:
            value = parsed.get(key)
            if isinstance(value, list):
                extracted = []
                for item in value:
                    if isinstance(item, str):
                        extracted.extend(item.split(","))
                if extracted:
                    return [
                        language_aliases.get(lang.strip().casefold(), lang.strip())
                        for lang in extracted
                        if lang.strip()
                    ]
            elif isinstance(value, str):
                return [
                    language_aliases.get(lang.strip().casefold(), lang.strip())
                    for lang in re.split(r"[,;\n]", value)
                    if lang.strip()
                ]

    extracted = []
    for match in re.finditer(r"\b(?:English|Irish|Romanian|French|Spanish|German|Italian|Portuguese|Dutch|Arabic|Chinese|Japanese|Korean|Polish|Czech|Greek|Russian|Ukrainian|Hungarian|Swedish|Norwegian|Danish|Finnish|Turkish|Latvian|Lithuanian|Slovak)\b(?:\s+(?:speaker|fluent|native|proficient|language))?", text, flags=re.IGNORECASE):
        candidate = match.group(0)
        cleaned = re.sub(r"\s+(?:speaker|fluent|native|proficient|language)$", "", candidate, flags=re.IGNORECASE).strip()
        normalized = language_aliases.get(cleaned.casefold(), cleaned.title())
        if normalized and normalized not in extracted:
            extracted.append(normalized)
    return extracted


def build_search_roles(
    target_roles: List[str],
    excluded_roles: List[str],
    cv_summaries: List[str],
) -> List[str]:
    """Combine explicit and CV-inferred roles, then remove excluded roles and include related role variants."""
    inferred_roles = []
    for cv_summary in cv_summaries:
        inferred_roles.extend(extract_cv_role_suggestions(cv_summary))

    expanded_roles: List[str] = []
    for role in [*target_roles, *inferred_roles]:
        expanded_roles.extend(_expand_role_variants(role))
    excluded = {role.casefold() for role in excluded_roles}
    filtered = [
        role
        for role in dict.fromkeys(expanded_roles)
        if role and role.casefold() not in excluded
    ]
    if filtered:
        return filtered
    return [role for role in dict.fromkeys([*target_roles, *inferred_roles]) if role and role.casefold() not in excluded]


def build_applied_job_preferences(jobs: List[Dict[str, Any]]) -> str:
    """Summarize the user's applied-job history for preference-aware search prompts."""
    applied_jobs = [
        job for job in jobs
        if str(job.get("Applied", "")).strip().lower() == "yes"
    ]
    if not applied_jobs:
        return "No applied-job history is available yet."

    role_categories = {
        "QA and testing": r"quality assurance|\bqa\b|test engineer|testing|tester|software quality|quality specialist|quality engineer",
        "Data and analytics": r"data analyst|data engineer|data operations|data quality|analytics|model operations|modelops",
        "Technical support": r"technical support|support engineer|support technician|application support|customer support|service delivery",
        "Operations": r"operations|assurance|capacity|content operations",
        "Business and systems analysis": r"business analyst|systems analyst|business applications",
        "Engineering and development": r"engineer|developer|software|automation|prompt",
        "Product and consulting": r"consultant|product specialist|product management",
    }
    category_counts = Counter()
    for job in applied_jobs:
        title = str(job.get("Job Title", "")).lower()
        matched_category = next(
            (category for category, pattern in role_categories.items() if re.search(pattern, title, re.IGNORECASE)),
            "Other",
        )
        category_counts[matched_category] += 1

    category_summary = ", ".join(
        f"{category} ({count})"
        for category, count in category_counts.most_common()
    )
    selected_roles = "\n".join(
        f"- {job.get('Job Title', 'Not specified')} — {job.get('Company', 'Not specified')}"
        for job in applied_jobs
    )
    return (
        f"The user has applied to {len(applied_jobs)} saved jobs. Their strongest demonstrated preferences "
        f"by role family are: {category_summary}. Use these as a strong ranking signal when selecting "
        "new roles, while still checking the CV, target roles, exclusions, location, freshness, and listing status. "
        "Applied-job history:\n" + selected_roles
    )


def update_verification_rows(rows: List[Dict[str, Any]], user_id: str) -> None:
    """Merge verification results into the saved CSV by title and company."""
    jobs = import_jobs_from_csv("job_matches.csv", user_id)
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
        if verification_status not in {"Active", "Expired"}:
            urls_to_check = {
                str(result.get("Official Listing URL") or "").strip(),
                str(job.get("Official Listing URL") or "").strip(),
                str(job.get("URL") or "").strip(),
                str(job.get("Original Listing URL") or "").strip(),
            }
            if any(_url_is_expired_sync(url) for url in urls_to_check):
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
    export_jobs_to_csv(jobs, "job_matches.csv", user_id)


async def run_saved_job_verification(verification_id: str, user_id: str) -> None:
    """Check saved roles in AI batches and persist results after each batch."""
    try:
        jobs = import_jobs_from_csv("job_matches.csv", user_id)
        jobs = [
            job for job in jobs
            if job.get("User Dismissed", "").lower() != "yes"
            and job.get("Applied", "").strip().lower() != "yes"
            and job.get("Verification Status", "").strip().lower() != "active"
            and job.get("User Status Override", "").lower() != "yes"
        ]
        batches = [jobs[index:index + 5] for index in range(0, len(jobs), 5)]
        for batch_index, batch in enumerate(batches, 1):
            progress = int(batch_index / max(1, len(batches)) * 90)
            update_search_status(verification_id, f"Verifying saved jobs batch {batch_index}/{len(batches)}...", progress)
            instructions = """
You verify saved job records using Google Search. Follow this order for every job:
1. Check the exact LinkedIn job posting first, including the direct LinkedIn URL when one is present.
2. Read the LinkedIn page status before checking any other source.
3. Only if LinkedIn does not provide a decisive result, check the exact job-board posting, then the
    employer's official careers website for the same exact title and location.
If LinkedIn says "No longer accepting applications", "applications are closed", "position is no
longer open", or gives any similar closure message, immediately classify the job as Expired. This
Expired result must not be overridden by a job-board copy, an official homepage, or an older search
snippet that appears active. Quote the closure wording and identify LinkedIn in Verification Notes.
Never mark Active from a generic careers homepage. Return ONLY a JSON array with Job Title, Company,
Verification Status, Verification Notes, and Official Listing URL.
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
            update_verification_rows(verification_results, user_id)
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
    user_id: str,
) -> None:
    prefs = firebase_utils.fetch_role_preferences(user_id)
    saved_location = prefs.get("target_location", "")
    max_posting_age_days = int(prefs.get("max_posting_age_days", 7))
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

        expanded_target_roles = build_search_roles(target_roles, excluded_roles, cv_summaries)
        if expanded_target_roles:
            update_search_status(search_id, f"Expanded search to {len(expanded_target_roles)} related role signals based on the CV profile.", 55)
        combined_summary = "\n\n--- NEXT CV PROFILE ---\n\n".join(cv_summaries)
        update_search_status(search_id, "Searching live jobs in batches...", 55)
        matched_jobs = await run_incremental_job_finder(
            combined_summary,
            search_id=search_id,
            target_roles=expanded_target_roles,
            excluded_roles=excluded_roles,
            cv_names=[filename for filename, _ in files],
            user_id=user_id,
            target_location=saved_location,
            max_posting_age_days=max_posting_age_days,
        )

        if not matched_jobs:
            existing_jobs = import_jobs_from_csv("job_matches.csv", user_id)
            if existing_jobs:
                matched_jobs = existing_jobs
                update_search_status(search_id, f"Keeping {len(existing_jobs)} previous valid matches...", 72)
            else:
                matched_jobs = []
                update_search_status(search_id, "No matching jobs were found in this search.", 72)

        if matched_jobs:
            update_search_status(search_id, f"Persisting {len(matched_jobs)} matches to CSV...", 82)
            append_jobs_to_csv(matched_jobs, "job_matches.csv", user_id=user_id)
        else:
            update_search_status(search_id, "Skipping CSV write because no valid jobs were returned.", 82)

        update_search_status(search_id, "Exporting workbook to Excel...", 90)
        output = io.BytesIO()
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = 'Job Matches'
        headers = list(dict.fromkeys(field for job in matched_jobs for field in job.keys()))
        if headers:
            worksheet.append(headers)
            for job in matched_jobs:
                worksheet.append([job.get(header, '') for header in headers])
        workbook.save(output)
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
    
    location_context = f"in {TARGET_LOCATION}" if TARGET_LOCATION else "in their target market"
    instructions = f"""
<<<<<<< HEAD
    You are an expert technical recruiter matching candidates for roles {location_context}.

    Analyze the provided resume and synthesize a detailed candidate profile:
    1. Core technical skills & primary tech stack
    2. Seniority level & total years of experience
    3. Key strengths and specializations (e.g., QA testing, AI operations, triage)
    4. Target role keywords that align with the candidate
    5. Candidate's current or target work location — extract this from the CV address, city, or
       any stated relocation/remote preference. State it explicitly as "Location: <city, country>"
       on its own line so it can be used for job search targeting.

    Be specific and detailed to help with job matching accuracy.
    """

    prompt = f"Analyze this CV and create a detailed candidate profile for job matching:\n\n{cv_text}"
=======
    You are an expert technical recruiter matching candidates for roles in {TARGET_LOCATION}.

    Analyze the provided resume and return strict JSON only.
    Required keys:
    - core_skills: array of technical skills and tools
    - seniority: string summarizing level and years of experience if stated
    - strengths: array of candidate specializations (e.g., QA testing, AI operations, triage)
    - matching_roles: array of likely job titles or role families that fit the candidate
    - languages: array of spoken or written languages explicitly mentioned in the CV (e.g., Romanian, English, Irish)

    Use evidence from the CV. Keep the output valid JSON with no markdown wrapper.
    """

    prompt = f"Analyze this CV and create a detailed candidate profile for {TARGET_LOCATION} job matching:\n\n{cv_text}"
>>>>>>> c83e656 (fix: broaden job search matching)
    
    response = await call_gemini_with_retry(
        instructions,
        prompt,
        use_google_search=False,
        max_retries=2,
        initial_delay=3,
    )
    logger.info("✅ Agent 1 completed: Candidate profile created")
    return response

@app.post("/api/jobs/recommend-cv")
async def recommend_cv_for_job(
    job_title: str = Form(...),
    company: str = Form(...),
    job_description: str = Form(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Re-run CV matching for a saved job against the user's current CV library."""
    cvs = firebase_utils.fetch_cvs(current_user["uid"])
    if not cvs:
        raise HTTPException(status_code=400, detail="No CVs found. Upload at least one CV in My CVs first.")

    if len(cvs) == 1:
        recommended = cvs[0]["name"]
    else:
        cv_profiles: List[tuple[str, str]] = []
        for cv in cvs:
            try:
                record, content = firebase_utils.download_cv(current_user["uid"], cv["id"])
                text = await extract_cv_text_from_bytes(cv["name"], content)
                summary = await run_cv_analyzer_agent(text)
                cv_profiles.append((cv["name"], summary[:2000]))
            except Exception:
                continue

        if not cv_profiles:
            raise HTTPException(status_code=400, detail="Could not read CV files from storage.")

        profiles_block = "\n\n".join(
            f"=== CV: {name} ===\n{summary}" for name, summary in cv_profiles
        )
        instructions = """You are an expert recruiter. Given a job description and several candidate
        CV profiles, identify which CV is the strongest match for the role. Reply with ONLY the exact
        CV filename — no explanation, no punctuation, just the filename."""
        prompt = (
            f"Job Title: {job_title}\nCompany: {company}\n\n"
            f"Job Description:\n{job_description[:3000]}\n\n"
            f"Candidate CV Profiles:\n{profiles_block}\n\n"
            f"Which CV filename best matches this job?"
        )
        response = await call_gemini_with_retry(instructions, prompt)
        recommended = cvs[0]["name"]
        for cv in cvs:
            if cv["name"].strip().lower() in response.strip().lower():
                recommended = cv["name"]
                break

    all_jobs = firebase_utils.fetch_jobs(current_user["uid"])
    for job in all_jobs:
        if job.get("Job Title") == job_title and job.get("Company") == company:
            job["Recommended CV"] = recommended
    firebase_utils.replace_jobs(all_jobs, current_user["uid"])

    return JSONResponse({"recommended_cv": recommended})


@app.post("/api/jobs/tailor-cv")
async def tailor_cv_for_job(
    cv_file: UploadFile = File(...),
    job_title: str = Form(...),
    company: str = Form(...),
    job_description: str = Form(...),
    user_prompt: str = Form(""),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Generate a truthful, keyword-aligned CV draft for one saved job."""
    content = await cv_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The selected CV file is empty.")

    cv_text = await extract_cv_text_from_bytes(cv_file.filename or "uploaded-cv", content)
    if user_prompt.strip():
        firebase_utils.save_prompt_preference(
            current_user["uid"], user_prompt, job_title, company, "tailor"
        )
    instructions = """
You tailor a candidate's CV for one specific job. Preserve the candidate's actual experience and
never invent employers, dates, achievements, tools, certifications, responsibilities, or metrics.
Your primary goal is strong ATS alignment without keyword stuffing. Work in two explicit passes:

PASS 1 - JOB DESCRIPTION KEYWORD ANALYSIS:
Create an internal, prioritized keyword map from the job description. Identify meaningful ATS terms,
not filler words: required hard skills, software and tools, programming languages, methodologies,
certifications, domain terminology, job-specific responsibilities, seniority terms, deliverables,
and action verbs. Distinguish must-have keywords from useful secondary keywords and note important
phrases that an ATS may match exactly.

PASS 2 - CV EVIDENCE MATCHING AND REWRITE:
Audit the source CV against that keyword map. Include as many must-have and secondary keywords as
possible, but only when the source CV provides truthful evidence for them. Use exact job-description
wording when supported, and use accurate synonyms when they describe the same experience. Prioritize
the strongest supported matches near the top, in the summary, skills, and relevant experience
bullets. Rewrite existing bullets to lead with clear action verbs, scope, tools, and measurable
outcomes already present in the source CV. Never add a keyword merely because it would improve ATS
matching if the CV does not support it.

Return only a complete CV draft, ready to paste into the same document format as the source CV.
Preserve the source CV's exact section names, section order, heading wording, job-entry order,
bullet style, indentation, paragraph breaks, and spacing pattern wherever possible. Keep headings,
emphasis markers, capitalization, and date/location lines in the same style as the source. If the
source uses bold headings or labels, represent that emphasis with the same visible convention in
the output; do not replace it with a new heading style. Preserve the original bullet character
or marker rather than switching between bullets and paragraphs.

Keep the document ATS-safe and single-column: do not use tables, columns, text boxes, headers/footers,
icons, graphics, emojis, decorative symbols, unusual fonts, hyperlinks disguised as text, or layout
instructions. Do not rename sections to generic headings when the source already has clear headings.
Keep the wording concise and scannable. Do not include a cover letter, keyword list detached from
evidence, match score, editing commentary, or claims unsupported by the source CV. If a job
requirement is not supported, do not add it; leave it out or make the gap clear rather than guessing.
"""
    instructions += f"""
USER'S SAVED TAILORING PREFERENCES:
{get_prompt_learning_context(current_user['uid'])}

Treat these as style preferences gathered from the same user. Apply them only when they do not conflict
with the source CV, current job, or truthfulness requirements.
"""
    prompt = f"""
Target job: {job_title}
Company: {company}

USER'S DIRECT TAILORING REQUEST:
{user_prompt.strip() or 'No additional request. Follow the ATS and source-format instructions above.'}

JOB DESCRIPTION:
{job_description}

SOURCE CV:
{cv_text}

ATS CHECK BEFORE RETURNING:
- Every keyword added must be supported by the source CV.
- The most relevant supported job-description keywords must appear naturally in the summary,
  skills, or experience sections.
- The output must remain plain text, single-column, and machine-readable.
- Preserve the source CV's section names, ordering, bullets, line breaks, spacing, and emphasis style.
- Preserve factual names, dates, employers, and qualifications from the source CV.
"""
    try:
        tailored_cv = await call_gemini_with_retry(
            instructions,
            prompt,
            use_google_search=False,
            max_retries=3,
            initial_delay=5,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"CV tailoring failed: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=503, detail="Could not generate the tailored CV.") from exc

    return JSONResponse({"tailored_cv": tailored_cv})


@app.post("/api/ai/prompt-preferences")
async def save_ai_prompt_preference(
    prompt: str = Form(...),
    job_title: str = Form(""),
    company: str = Form(""),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Enter a tailoring preference first.")
    record = firebase_utils.save_prompt_preference(
        current_user["uid"], prompt, job_title, company, "saved_preference"
    )
    return JSONResponse({"saved": True, "preference": record})


@app.post("/api/jobs/tailor-cv/chat")
async def ask_cv_tailoring_question(
    cv_file: UploadFile = File(...),
    job_title: str = Form(...),
    company: str = Form(...),
    job_description: str = Form(...),
    user_prompt: str = Form(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Answer a direct CV-tailoring question for one job without generating a full CV."""
    if not user_prompt.strip():
        raise HTTPException(status_code=400, detail="Ask a tailoring question first.")

    content = await cv_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The selected CV file is empty.")

    cv_text = await extract_cv_text_from_bytes(cv_file.filename or "uploaded-cv", content)
    firebase_utils.save_prompt_preference(
        current_user["uid"], user_prompt, job_title, company, "question"
    )
    instructions = """
You are a CV tailoring advisor. Answer the user's direct question using the job description and source
CV. First identify meaningful ATS keywords and requirements in the job description, then check which
are supported by the CV. Give specific, actionable advice and exact suggested wording where useful.
Never invent experience, tools, employers, dates, certifications, metrics, or achievements. Preserve
the source CV's section names, bullet style, spacing pattern, and emphasis conventions. Be concise.
This is a one-request interaction: do not claim that the user's prompt trains, fine-tunes, or changes
the underlying model.
"""
    instructions += f"""
USER'S SAVED TAILORING PREFERENCES:
{get_prompt_learning_context(current_user['uid'])}

Use these as secondary style preferences, while prioritizing the current question and truthful CV evidence.
"""
    prompt = f"""
Target job: {job_title}
Company: {company}

USER QUESTION:
{user_prompt.strip()}

JOB DESCRIPTION:
{job_description}

SOURCE CV:
{cv_text}
"""
    try:
        answer = await call_gemini_with_retry(
            instructions,
            prompt,
            use_google_search=False,
            max_retries=3,
            initial_delay=5,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"CV tailoring chat failed: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=503, detail="Could not answer the tailoring question.") from exc

    firebase_utils.save_prompt_preference(
        current_user["uid"], user_prompt, job_title, company, "question", answer
    )

    return JSONResponse({"answer": answer})


async def run_incremental_job_finder(
    cv_summary: str,
    search_id: str | None = None,
    target_roles: List[str] | None = None,
    excluded_roles: List[str] | None = None,
    cv_names: List[str] | None = None,
    user_id: str | None = None,
    target_location: str = "",
    max_posting_age_days: int = 7,
) -> List[Dict[str, Any]]:
    """
    AGENT 2: Searches for jobs in batches using Google Search and matches to candidate.

    Args:
        cv_summary: Candidate profile from Agent 1
        search_id: Optional active search ID for live progress updates
        target_location: User-configured location; falls back to CV-inferred location when empty.

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
    existing_jobs = import_jobs_from_csv("job_matches.csv", user_id)
    applied_job_preferences = build_applied_job_preferences(existing_jobs)
    saved_job_keys = {
        (
            str(job.get("Job Title", "")).strip().casefold(),
            str(job.get("Company", "")).strip().casefold(),
        )
        for job in existing_jobs
    }
    # Only show active non-dismissed jobs in the Gemini ledger — expired and dismissed jobs
    # remain in saved_job_keys for code-level dedup but don't clutter the prompt or
    # prevent Gemini from suggesting fresh postings for roles that previously expired.
    active_jobs = [
        job for job in existing_jobs
        if job.get("User Dismissed", "").strip().lower() != "yes"
        and job.get("Verification Status", "").strip().lower() != "expired"
    ]
    existing_jobs_summary = "\n".join(
        f"- {job.get('Job Title', 'Not specified')} — {job.get('Company', 'Not specified')}"
        for job in active_jobs
    ) or "None"

    def keep_new_jobs(candidate_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique_jobs = []
        for job in candidate_jobs:
            key = (
                str(job.get("Job Title", "")).strip().casefold(),
                str(job.get("Company", "")).strip().casefold(),
            )
            if key in saved_job_keys:
                continue
            saved_job_keys.add(key)
            unique_jobs.append(job)
        return unique_jobs
    
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
        
location_str = target_location.strip() or TARGET_LOCATION or "the location stated in the candidate's profile above"
language_signals = extract_cv_languages(cv_summary)
language_hint = (
    f" Language signals from the CV: {', '.join(language_signals)}. Include relevant bilingual language requirements when they align with the candidate profile."
    if language_signals
    else ""
)

instructions = f"""
You are an automated career matching agent using Google Search.

Search for ACTIVE open job listings specifically in **{location_str}** and across Irish hiring boards relevant to Dublin and Ireland, including IrishJobs, Jobs.ie, MCS Group, Sigmar Recruitment, Morgan McKinley, LinkedIn, Indeed, Greenhouse, Workday, and similar board sources.

Search roles and close variants:
[{batch_roles_str}]

STRICT EXCLUSION LIST (DO NOT INCLUDE ANY OF THESE ROLES):
[{excluded_str}]

CRITICAL REQUIREMENTS:
1. Only return jobs posted within the last {max_posting_age_days} days.
2. Filter out any jobs older than {max_posting_age_days} days.
2a. Before returning any result, compare its normalized job title and company against the
    complete saved-job ledger below. Do not return duplicates, even if the new URL or source
    is different. Review the entire ledger, not only the current search batch.
3. If the listing page says "No longer accepting applications", "applications are closed",
    "position is no longer open", "role is no longer active", or any equivalent closure note,
    treat it as Expired and do not save it as an active job. Ignore these listings entirely.
4. Match candidate skills from profile: {cv_summary[:300]}...
5. Treat the requested roles as primary search signals, but do not require an exact title match if the job is clearly aligned with the candidate profile and role family. Close variants such as QA, test engineer, support engineer, product support, systems analyst, incident analyst, implementation specialist, customer success, and other related titles are valid when they match the CV experience.
6. {language_hint if language_hint else 'Use the CV language signals when they matter for language-based roles but do not exclude otherwise suitable jobs.'}
7. Return the exact direct URL of each job listing from the search result; never use N/A,
    a company homepage, a search page, or a fabricated URL. If no direct listing URL is
    available, include the job with "Not specified" and mark the URL status accordingly.
8. Extract the posting date when visible. Use "Not specified" only when the listing does
    not show a date. Normalize working type to exactly Remote, Hybrid, On-site, or
    Not specified.
9. Extract the salary or compensation exactly as shown. Use "Not specified" when it is
    not available; do not estimate or invent salary.
10. Select the best matching CV filename from this list and return it exactly:
    [{", ".join(cv_names)}]
11. Provide a concrete recommendation for tailoring that selected CV to this job,
    including which skills, experience, or keywords to emphasize.
12. Extract the complete job description from the original listing, preserving all
    available sections, paragraphs, responsibilities, requirements, qualifications,
    benefits, and other visible content. Do not summarize or shorten it. Do not invent
    details. The description must contain at least 500 characters of source text. If the
    full description cannot be retrieved, do not return that job.
13. Check sources in this strict order: first the exact LinkedIn posting, then the exact
    job-board posting (Indeed, IrishJobs, Jobs.ie, Greenhouse, Workday, or another board),
    then the employer's official careers listing. Inspect the LinkedIn page status before using
    any other source. If LinkedIn says "No longer accepting applications", "applications
    are closed", "position is no longer open", or similar, classify the role as Expired,
    quote that wording in the verification notes, and do not return or save it as Active.
    A job-board copy, official homepage, or older search snippet must never override a
    LinkedIn closure message. Do not treat a company careers homepage, a generic
    Greenhouse board, or a different job ID as verification. The official page must show
    the exact job title and employer; otherwise mark it No.
14. Set Listing Source to Official company website or the job-board name. Set Official
    Listing Verified to Yes only when the exact role is found on the official employer
    site; otherwise set it to No and put Not specified in Official Listing URL.
15. Always return Original Listing URL as the exact direct URL where the job was found.
    Return the official URL in URL when verified; otherwise return the original job-board
    URL in URL.
16. Use this applied-job history as a strong preference signal. Prioritize new jobs that
    resemble the user's repeatedly applied role families and title patterns, but do not
    assume that every previously applied role is suitable. The CV, target roles, exclusion
    list, location, freshness, exact listing identity, expiry checks, and language fit remain
    mandatory.
17. Applied-job preference profile:
{applied_job_preferences}
18. Existing saved-job ledger for duplicate checking:
{existing_jobs_summary}

FIT SCORE RUBRIC — follow this exactly when setting "Fit Score (%)":
Start at 100 and apply the following deductions before assigning the score.

HARD REQUIREMENT PENALTIES (apply each that is unmet):
- Named proprietary tool/platform the candidate has no experience with (e.g. SAP, Salesforce,
  Hogan, Unibanks, Workday, ServiceNow, specific CMS): -20 per unmet tool, max -40
- Required years of experience the candidate clearly does not meet (e.g. "5+ years" when
  candidate has 1-2 years in that discipline): -20 per unmet requirement, max -30
- Mandatory degree or certification not present on the CV (e.g. "postgraduate required",
  "CPA required", "CISSP required"): -25
- Required domain-specific background the candidate has none of (e.g. "pharma GxP experience
  required", "financial services background required"): -20
- Automation or testing framework experience explicitly required but candidate's experience
  is clearly in a different form of automation (e.g. role requires Playwright/Selenium/
  Cypress test automation; candidate has workflow/process automation only): -20

OVERMATCHING GUARD — keyword presence alone is not a match:
- Do not award credit for a skill or tool if the CV only mentions it in passing or lists it
  without demonstrating professional depth. Only count skills with clear evidence of sustained
  use (multiple roles, quantified outcomes, or project ownership).
- Do not treat "QA" as equivalent to "test automation". Do not treat "Python scripting" as
  equivalent to "software engineering". Do not treat "data analysis" as equivalent to
  "BI/data analytics tooling experience". Match the depth, not just the keyword.

SCORING FLOOR:
- Any job with 2 or more unmet hard requirements must score 65% or below.
- Any job with a named proprietary tool requirement the candidate clearly lacks must score
  70% or below, regardless of other matches.

For "Match Reasons": write 2-4 sentences explaining the strongest genuine overlaps between
the candidate profile and this specific role. Be honest — do not pad with generic claims.

For "Missing Requirements": list every hard requirement from the job description that the
candidate does not clearly meet. Use a bullet list. Write "None identified" if there are
no meaningful gaps. This field must reflect the actual job description, not generic advice.

Output ONLY a valid JSON array (no markdown, no ```json wrapper):
[
  {{
    "Job Title": "Exact Job Title",
    "Company": "Company Name",
    "Location": "Location",
    "Fit Score (%)": "e.g., 85%",
    "Match Reasons": "2-4 sentences on genuine overlaps",
    "Missing Requirements": "Bullet list of unmet hard requirements, or None identified",
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
    "Working Type": "Remote, Hybrid, On-site, or Not specified",
    "Salary": "Salary or compensation exactly as listed, or Not specified"
  }}
]
"""

prompt = (
    f"Search Google for job listings in {location_str} and Ireland for these role signals: {batch_roles_str}. "
    f"Look across relevant Irish job boards and employer pages, not only exact-title searches. "
    f"Only include jobs posted in the last {max_posting_age_days} days. "
    f"Prioritize the user's demonstrated applied-job preferences described in the instructions. "
    f"Do not return any title/company pair already present in the complete saved-job ledger included in your instructions. "
    f"Match them against this candidate profile and score strictly using the rubric in your instructions:\n{cv_summary}{language_hint}"
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
                    valid_jobs = keep_new_jobs(valid_jobs)
                    all_jobs.extend(valid_jobs)
                    if len(valid_jobs) > 0:
                        if user_id:
                            append_jobs_to_csv(valid_jobs, "job_matches.csv", user_id=user_id)
                        else:
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
                valid_jobs = keep_new_jobs(valid_jobs)
                all_jobs.extend(valid_jobs)
                if valid_jobs:
                    if user_id:
                        append_jobs_to_csv(valid_jobs, "job_matches.csv", user_id=user_id)
                    else:
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


def has_extractable_cv_text(text: str) -> bool:
    """Return whether extracted content contains enough readable CV text to analyze."""
    return len(re.findall(r"[A-Za-z0-9]", text)) >= 20


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

            if not has_extractable_cv_text(cv_text):
                logger.warning("PDF extracted but contains no readable text")
                raise HTTPException(
                    status_code=422,
                    detail="PDF contains no readable text. It may be scanned or image-only; upload a text-based PDF or DOCX.",
                )

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
                raise HTTPException(
                    status_code=422,
                    detail="DOCX contains no readable text. Check that the document contains selectable text.",
                )

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

            if not has_extractable_cv_text(cv_text):
                logger.warning("DOCX extracted but contains no readable text")
                raise HTTPException(
                    status_code=422,
                    detail="DOCX contains no readable text. Check that the document contains selectable text.",
                )

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
    cv_ids: str | None = Form(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Start a background job search and return a live search ID for polling."""
    uploaded_files = list(files)
    if file is not None:
        uploaded_files.append(file)
    file_payloads = [(uploaded_file.filename or "unknown.pdf", await uploaded_file.read()) for uploaded_file in uploaded_files]
    selected_cv_ids = [cv_id.strip() for cv_id in (cv_ids or "").split(",") if cv_id.strip()]
    for cv_id in selected_cv_ids:
        try:
            cv_record, cv_content = firebase_utils.download_cv(current_user["uid"], cv_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Selected CV not found: {cv_id}") from exc
        file_payloads.append((str(cv_record.get("name") or "uploaded-cv.pdf"), cv_content))
    if not file_payloads:
        raise HTTPException(status_code=400, detail="Upload at least one PDF or DOCX CV file")

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
        "user_id": current_user["uid"],
    }
    asyncio.create_task(run_search_pipeline(
        search_id,
        file_payloads,
        parsed_target_roles,
        parsed_excluded_roles,
        reuse_cv_analysis,
        current_user["uid"],
    ))
    return JSONResponse({
        "search_id": search_id,
        "status": "queued",
        "message": f"Search started for {len(file_payloads)} CV(s)",
    })


@app.get("/api/cvs")
async def get_cvs(current_user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    try:
        return JSONResponse({"cvs": firebase_utils.fetch_cvs(current_user["uid"])})
    except Exception as exc:
        logger.error("Error fetching CVs: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch imported CVs") from exc


@app.post("/api/cvs")
async def upload_cvs(
    files: List[UploadFile] = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    saved_cvs = []
    for uploaded_file in files:
        filename = uploaded_file.filename or "uploaded-cv.pdf"
        if not filename.lower().endswith((".pdf", ".docx")):
            raise HTTPException(status_code=400, detail="Only PDF and DOCX CVs are supported")
        content = await uploaded_file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Each CV must be 10MB or smaller")
        try:
            saved_cvs.append(firebase_utils.save_cv(
                current_user["uid"],
                filename,
                uploaded_file.content_type or "application/octet-stream",
                content,
            ))
        except GoogleNotFound as exc:
            raise HTTPException(
                status_code=503,
                detail="Firebase Storage is not enabled for this project. Open Firebase Console > Storage and click Get started, then retry.",
            ) from exc
    return JSONResponse({"cvs": saved_cvs})


@app.delete("/api/cvs/{cv_id}")
async def delete_cv(cv_id: str, current_user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    try:
        firebase_utils.delete_cv(current_user["uid"], cv_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="CV not found") from exc
    return JSONResponse({"deleted": True, "cv_id": cv_id})


@app.patch("/api/cvs/{cv_id}")
async def rename_cv(cv_id: str, name: str = Form(...), current_user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    new_name = name.strip()
    if not new_name.lower().endswith((".pdf", ".docx")):
        raise HTTPException(status_code=400, detail="CV name must end with .pdf or .docx")
    if "/" in new_name or "\\" in new_name:
        raise HTTPException(status_code=400, detail="CV name cannot contain folder separators")
    try:
        record = firebase_utils.rename_cv(current_user["uid"], cv_id, new_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="CV not found") from exc
    return JSONResponse({"cv": record})


@app.get("/api/cvs/{cv_id}/content")
async def get_cv_content(cv_id: str, current_user: Dict[str, Any] = Depends(get_current_user)) -> StreamingResponse:
    try:
        record, content = firebase_utils.download_cv(current_user["uid"], cv_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="CV not found") from exc
    return StreamingResponse(
        io.BytesIO(content),
        media_type=str(record.get("content_type") or "application/octet-stream"),
        headers={"Content-Disposition": f"inline; filename=\"{record.get('name', 'cv')}\""},
    )


@app.get("/api/search/status/{search_id}")
async def get_search_status(search_id: str, current_user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    """Return the current progress and log stream for an active search."""
    status = ACTIVE_SEARCHES.get(search_id)
    if not status or status.get("user_id") != current_user["uid"]:
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
async def get_search_result(search_id: str, current_user: Dict[str, Any] = Depends(get_current_user)) -> StreamingResponse:
    """Download the Excel workbook for a completed search."""
    status = ACTIVE_SEARCHES.get(search_id)
    if not status or status.get("user_id") != current_user["uid"] or status.get("status") != "complete":
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
async def get_jobs(current_user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    """
    Fetch all jobs from CSV file.
    
    Returns:
        JSON array of job objects
    """
    try:
        jobs = import_jobs_from_csv("job_matches.csv", current_user["uid"])
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


@app.get("/api/preferences/roles")
async def get_role_preferences(current_user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    return JSONResponse(firebase_utils.fetch_role_preferences(current_user["uid"]))


@app.put("/api/preferences/roles")
async def put_role_preferences(
    target_roles: str = Form(""),
    excluded_roles: str = Form(""),
    target_location: str = Form(""),
    max_posting_age_days: int = Form(7),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    split_roles = lambda value: list(dict.fromkeys(role.strip() for role in re.split(r"[,\n]", value) if role.strip()))
    record = firebase_utils.save_role_preferences(current_user["uid"], split_roles(target_roles), split_roles(excluded_roles), target_location, max_posting_age_days)
    return JSONResponse(record)


@app.post("/api/jobs/import-csv")
async def import_existing_csv_jobs(current_user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    """Migrate local job_matches.csv records into the signed-in user's store."""
    local_jobs = import_local_jobs_from_csv("job_matches.csv")
    if not local_jobs:
        return JSONResponse({"imported": 0, "message": "No local job_matches.csv records found."})
    append_jobs_to_csv(local_jobs, "job_matches.csv", user_id=current_user["uid"])
    return JSONResponse({"imported": len(local_jobs), "message": f"Imported {len(local_jobs)} CSV jobs."})


@app.post("/api/jobs/dismiss")
async def dismiss_job(
    job_title: str = Form(...),
    company: str = Form(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Hide a job from the listing while retaining it in CSV for deduplication."""
    dismissed = dismiss_job_in_csv(job_title, company, "job_matches.csv", current_user["uid"])
    if not dismissed:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse({"dismissed": True, "message": "Job dismissed and retained in CSV"})


@app.post("/api/jobs/dismiss-expired")
async def dismiss_all_expired_jobs(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Dismiss all jobs marked as Expired, keeping them for deduplication."""
    count = dismiss_expired_jobs_in_csv("job_matches.csv", current_user["uid"])
    return JSONResponse({"dismissed": count})


@app.post("/api/jobs/update-url")
async def update_job_url(
    job_title: str = Form(...),
    company: str = Form(...),
    url: str = Form(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Save a user-confirmed preferred listing URL for a job."""
    if not re.match(r"^https?://[^\s]+$", url.strip(), re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Enter a valid http(s) URL")
    updated = update_job_url_in_csv(job_title, company, url.strip(), "job_matches.csv", current_user["uid"])
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse({"updated": True, "url": url.strip()})


@app.post("/api/jobs/applied")
async def update_job_applied(
    job_title: str = Form(...),
    company: str = Form(...),
    applied: bool = Form(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Persist the user's applied/not-applied status for a job."""
    updated = update_job_applied_in_csv(job_title, company, applied, "job_matches.csv", current_user["uid"])
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse({"updated": True, "applied": applied})


@app.post("/api/jobs/status")
async def update_job_status(
    job_title: str = Form(...),
    company: str = Form(...),
    status: str = Form(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Persist a manual verification status for a job row."""
    if not status.strip():
        raise HTTPException(status_code=400, detail="Status is required")

    updated = update_job_status_in_csv(job_title, company, status.strip(), "job_matches.csv", current_user["uid"])
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse({"updated": True, "status": status.strip()})


@app.post("/api/jobs/verify/start")
async def start_job_verification(current_user: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    """Start AI verification of the saved job listings."""
    verification_id = f"verify-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    ACTIVE_SEARCHES[verification_id] = {
        "status": "queued",
        "progress": 0,
        "message": "Starting saved job verification...",
        "logs": ["Starting saved job verification..."],
        "user_id": current_user["uid"],
    }
    asyncio.create_task(run_saved_job_verification(verification_id, current_user["uid"]))
    return JSONResponse({"verification_id": verification_id, "status": "queued"})

