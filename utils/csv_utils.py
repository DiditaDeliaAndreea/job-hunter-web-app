"""CSV data export/import utilities for job matching application."""

import csv
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from utils import firebase_utils

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CSV_FIELDS = [
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
    "First Seen Date",
    "Is Actively Recruiting",
]


def normalize_csv_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Add fields introduced after older CSV files were created."""
    normalized = {field: job.get(field) or "Not specified" for field in CSV_FIELDS}
    normalized["URL"] = job.get("URL") or "Not specified"
    normalized["Original Listing URL"] = job.get("Original Listing URL") or normalized["URL"]
    normalized["First Seen Date"] = job.get("First Seen Date") or date.today().isoformat()
    normalized["Is Actively Recruiting"] = job.get("Is Actively Recruiting") or "Unknown"
    return normalized


def export_jobs_to_csv(jobs: List[Dict[str, Any]], filename: str = "job_matches.csv", user_id: str | None = None) -> str:
    """
    Export job data to CSV file.
    
    Args:
        jobs: List of job dictionaries
        filename: Output filename (saved to data/ directory)
        
    Returns:
        Path to created CSV file
    """
    if firebase_utils.is_configured() and user_id:
        firebase_utils.replace_jobs(jobs, user_id or "")
        return "firebase://jobs"

    filepath = DATA_DIR / filename
    
    if not jobs:
        logger.warning("No jobs to export")
        return str(filepath)
    
    headers = CSV_FIELDS
    
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            writer.writerows(jobs)
        
        logger.info(f"✅ Exported {len(jobs)} jobs to {filepath}")
        return str(filepath)
    
    except Exception as e:
        logger.error(f"❌ Failed to export CSV: {e}")
        raise


def import_jobs_from_csv(filename: str = "job_matches.csv", user_id: str | None = None) -> List[Dict[str, Any]]:
    """
    Import job data from CSV file.
    
    Args:
        filename: Input filename (from data/ directory)
        
    Returns:
        List of job dictionaries
    """
    if firebase_utils.is_configured() and user_id:
        return firebase_utils.fetch_jobs(user_id or "")

    filepath = DATA_DIR / filename
    
    if not filepath.exists():
        logger.warning(f"File not found: {filepath}")
        return []
    
    try:
        jobs = []
        with open(filepath, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                jobs.append(normalize_csv_job(dict(row)))
        
        logger.info(f"✅ Imported {len(jobs)} jobs from {filepath}")
        return jobs
    
    except Exception as e:
        logger.error(f"❌ Failed to import CSV: {e}")
        return []


def import_local_jobs_from_csv(filename: str = "job_matches.csv") -> List[Dict[str, Any]]:
    """Read the local CSV directly, even when Firebase persistence is enabled."""
    filepath = DATA_DIR / filename
    if not filepath.exists():
        return []
    with open(filepath, 'r', encoding='utf-8') as csvfile:
        return [normalize_csv_job(dict(row)) for row in csv.DictReader(csvfile)]


def append_jobs_to_csv(jobs: List[Dict[str, Any]], filename: str = "job_matches.csv", user_id: str | None = None) -> str:
    """
    Append jobs to existing CSV file (avoiding duplicates).
    
    Args:
        jobs: List of job dictionaries to append
        filename: CSV filename
        
    Returns:
        Path to CSV file
    """
    if firebase_utils.is_configured() and user_id:
        firebase_utils.append_jobs(jobs, user_id or "")
        return "firebase://jobs"

    filepath = DATA_DIR / filename
    
    if not jobs:
        logger.warning("No jobs to append")
        return str(filepath)
    
    try:
        # Read existing jobs
        existing_jobs = import_jobs_from_csv(filename)
        
        # Create set of existing job keys to avoid duplicates
        existing_keys = set()
        for job in existing_jobs:
            key = (job.get("Job Title", "").lower(), job.get("Company", "").lower())
            existing_keys.add(key)
        
        # Filter new jobs
        new_jobs_to_add = []
        for job in jobs:
            key = (job.get("Job Title", "").lower(), job.get("Company", "").lower())
            if key not in existing_keys:
                new_jobs_to_add.append(normalize_csv_job(job))
                existing_keys.add(key)
        
        # Append new jobs
        if new_jobs_to_add:
            all_jobs = existing_jobs + new_jobs_to_add
            export_jobs_to_csv(all_jobs, filename)
            logger.info(f"✅ Appended {len(new_jobs_to_add)} new unique jobs to {filename}")
        else:
            logger.info("ℹ️ No new unique jobs to append")
        
        return str(filepath)
    
    except Exception as e:
        logger.error(f"❌ Failed to append CSV: {e}")
        raise


def dismiss_expired_jobs_in_csv(filename: str = "job_matches.csv", user_id: str | None = None) -> int:
    """Mark all verified-expired jobs as dismissed. Returns the count dismissed."""
    jobs = import_jobs_from_csv(filename, user_id)
    count = 0
    for job in jobs:
        if (
            job.get("Verification Status", "").strip().lower() == "expired"
            and job.get("User Dismissed", "").strip().lower() != "yes"
        ):
            job["User Dismissed"] = "Yes"
            count += 1
    if count:
        export_jobs_to_csv(jobs, filename, user_id)
    return count


def dismiss_job_in_csv(job_title: str, company: str, filename: str = "job_matches.csv", user_id: str | None = None) -> bool:
    """Mark a job as dismissed without deleting it, preventing future re-addition."""
    jobs = import_jobs_from_csv(filename, user_id)
    target_key = (job_title.strip().lower(), company.strip().lower())
    updated = False

    for job in jobs:
        key = (job.get("Job Title", "").strip().lower(), job.get("Company", "").strip().lower())
        if key == target_key:
            job["User Dismissed"] = "Yes"
            updated = True

    if updated:
        export_jobs_to_csv(jobs, filename, user_id)
    return updated


def update_job_url_in_csv(job_title: str, company: str, url: str, filename: str = "job_matches.csv", user_id: str | None = None) -> bool:
    """Set a user-confirmed preferred URL without replacing the original source URL."""
    jobs = import_jobs_from_csv(filename, user_id)
    target_key = (job_title.strip().lower(), company.strip().lower())
    updated = False

    for job in jobs:
        key = (job.get("Job Title", "").strip().lower(), job.get("Company", "").strip().lower())
        if key == target_key:
            job["URL"] = url
            job["Official Listing URL"] = url
            job["Official Listing Verified"] = "Yes"
            job["Listing Source"] = "User-provided preferred listing"
            job["URL Check Status"] = "User updated URL; not automatically checked"
            updated = True

    if updated:
        export_jobs_to_csv(jobs, filename, user_id)
    return updated


def update_job_applied_in_csv(job_title: str, company: str, applied: bool, filename: str = "job_matches.csv", user_id: str | None = None) -> bool:
    """Persist whether the user applied to a job."""
    jobs = import_jobs_from_csv(filename, user_id)
    target_key = (job_title.strip().lower(), company.strip().lower())
    updated = False

    for job in jobs:
        key = (job.get("Job Title", "").strip().lower(), job.get("Company", "").strip().lower())
        if key == target_key:
            job["Applied"] = "Yes" if applied else "No"
            updated = True

    if updated:
        export_jobs_to_csv(jobs, filename, user_id)
    return updated


def update_job_status_in_csv(job_title: str, company: str, status: str, filename: str = "job_matches.csv", user_id: str | None = None) -> bool:
    """Persist a user-adjusted verification status and protect it from AI verification."""
    jobs = import_jobs_from_csv(filename, user_id)
    target_key = (job_title.strip().lower(), company.strip().lower())
    updated = False

    for job in jobs:
        key = (job.get("Job Title", "").strip().lower(), job.get("Company", "").strip().lower())
        if key == target_key:
            normalized_status = str(status or "Not verified").strip() or "Not verified"
            job["Verification Status"] = normalized_status
            job["User Status Override"] = "Yes"
            job["Verification Notes"] = job.get("Verification Notes") or "User-adjusted status"
            updated = True

    if updated:
        export_jobs_to_csv(jobs, filename, user_id)
    return updated


def get_csv_stats(filename: str = "job_matches.csv") -> Dict[str, Any]:
    """
    Get statistics about a CSV file.
    
    Args:
        filename: CSV filename
        
    Returns:
        Dictionary with file statistics
    """
    filepath = DATA_DIR / filename
    jobs = import_jobs_from_csv(filename)
    
    if not jobs:
        return {"file": str(filepath), "total_jobs": 0, "exists": filepath.exists()}
    
    # Calculate average fit score
    fit_scores = []
    for job in jobs:
        score_str = job.get("Fit Score (%)", "0%").rstrip('%')
        try:
            fit_scores.append(float(score_str))
        except ValueError:
            pass
    
    avg_score = sum(fit_scores) / len(fit_scores) if fit_scores else 0
    
    return {
        "file": str(filepath),
        "total_jobs": len(jobs),
        "exists": filepath.exists(),
        "average_fit_score": f"{avg_score:.1f}%",
        "headers": list(jobs[0].keys()) if jobs else []
    }
