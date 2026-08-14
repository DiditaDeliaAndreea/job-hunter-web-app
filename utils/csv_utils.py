"""CSV data export/import utilities for job matching application."""

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List

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


def normalize_csv_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Add fields introduced after older CSV files were created."""
    normalized = {field: job.get(field) or "Not specified" for field in CSV_FIELDS}
    normalized["URL"] = job.get("URL") or "Not specified"
    normalized["Original Listing URL"] = job.get("Original Listing URL") or normalized["URL"]
    return normalized


def export_jobs_to_csv(jobs: List[Dict[str, Any]], filename: str = "job_matches.csv") -> str:
    """
    Export job data to CSV file.
    
    Args:
        jobs: List of job dictionaries
        filename: Output filename (saved to data/ directory)
        
    Returns:
        Path to created CSV file
    """
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


def import_jobs_from_csv(filename: str = "job_matches.csv") -> List[Dict[str, Any]]:
    """
    Import job data from CSV file.
    
    Args:
        filename: Input filename (from data/ directory)
        
    Returns:
        List of job dictionaries
    """
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


def append_jobs_to_csv(jobs: List[Dict[str, Any]], filename: str = "job_matches.csv") -> str:
    """
    Append jobs to existing CSV file (avoiding duplicates).
    
    Args:
        jobs: List of job dictionaries to append
        filename: CSV filename
        
    Returns:
        Path to CSV file
    """
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


def dismiss_job_in_csv(job_title: str, company: str, filename: str = "job_matches.csv") -> bool:
    """Mark a job as dismissed without deleting it, preventing future re-addition."""
    jobs = import_jobs_from_csv(filename)
    target_key = (job_title.strip().lower(), company.strip().lower())
    updated = False

    for job in jobs:
        key = (job.get("Job Title", "").strip().lower(), job.get("Company", "").strip().lower())
        if key == target_key:
            job["User Dismissed"] = "Yes"
            updated = True

    if updated:
        export_jobs_to_csv(jobs, filename)
    return updated


def update_job_url_in_csv(job_title: str, company: str, url: str, filename: str = "job_matches.csv") -> bool:
    """Set a user-confirmed preferred URL without replacing the original source URL."""
    jobs = import_jobs_from_csv(filename)
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
        export_jobs_to_csv(jobs, filename)
    return updated


def update_job_applied_in_csv(job_title: str, company: str, applied: bool, filename: str = "job_matches.csv") -> bool:
    """Persist whether the user applied to a job."""
    jobs = import_jobs_from_csv(filename)
    target_key = (job_title.strip().lower(), company.strip().lower())
    updated = False

    for job in jobs:
        key = (job.get("Job Title", "").strip().lower(), job.get("Company", "").strip().lower())
        if key == target_key:
            job["Applied"] = "Yes" if applied else "No"
            updated = True

    if updated:
        export_jobs_to_csv(jobs, filename)
    return updated


def update_job_status_in_csv(job_title: str, company: str, status: str, filename: str = "job_matches.csv") -> bool:
    """Persist a user-adjusted verification status and protect it from AI verification."""
    jobs = import_jobs_from_csv(filename)
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
        export_jobs_to_csv(jobs, filename)
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
