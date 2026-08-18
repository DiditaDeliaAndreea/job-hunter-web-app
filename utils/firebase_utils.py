"""Firebase Firestore persistence for normalized job records."""

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List

import firebase_admin
from firebase_admin import credentials, firestore, storage
from firebase_admin import auth

logger = logging.getLogger(__name__)

_database = None
_database_lock = Lock()
COLLECTION_NAME = "jobs"
DIAGNOSTIC_LOGS_COLLECTION = "diagnostic_logs"


def is_configured() -> bool:
    return bool(os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))


def _get_database():
    global _database
    if _database is None:
        with _database_lock:
            if _database is None:
                service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
                credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
                if service_account_json:
                    try:
                        service_account_info = json.loads(service_account_json)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON must contain valid JSON") from exc
                elif credentials_path:
                    path = Path(credentials_path)
                    if not path.exists():
                        raise RuntimeError(f"Firebase credentials file not found: {path}")
                    try:
                        service_account_info = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as exc:
                        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS must point to a valid JSON key file") from exc
                else:
                    raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON or GOOGLE_APPLICATION_CREDENTIALS must be configured")

                if not firebase_admin._apps:
                    options = {}
                    if os.getenv("FIREBASE_STORAGE_BUCKET"):
                        options["storageBucket"] = os.getenv("FIREBASE_STORAGE_BUCKET")
                    firebase_admin.initialize_app(credentials.Certificate(service_account_info), options)
                _database = firestore.client()
    return _database


def verify_id_token(id_token: str) -> Dict[str, Any]:
    _get_database()
    return auth.verify_id_token(id_token)


def job_id(job: Dict[str, Any]) -> str:
    key = "|".join([
        str(job.get("Job Title", "")).strip().lower(),
        str(job.get("Company", "")).strip().lower(),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _jobs_collection(user_id: str):
    if not user_id:
        raise ValueError("A Firebase user ID is required for job persistence")
    return _get_database().collection("users").document(user_id).collection(COLLECTION_NAME)


def fetch_jobs(user_id: str) -> List[Dict[str, Any]]:
    documents = _jobs_collection(user_id).stream()
    return [dict(document.to_dict().get("data") or {}) for document in documents]


def replace_jobs(jobs: List[Dict[str, Any]], user_id: str) -> None:
    database = _get_database()
    collection = _jobs_collection(user_id)
    for start in range(0, len(jobs), 400):
        batch = database.batch()
        for job in jobs[start:start + 400]:
            batch.set(collection.document(job_id(job)), {"data": job})
        batch.commit()


def append_jobs(jobs: List[Dict[str, Any]], user_id: str) -> None:
    existing = fetch_jobs(user_id)
    existing_keys = {
        (str(job.get("Job Title", "")).strip().lower(), str(job.get("Company", "")).strip().lower())
        for job in existing
    }
    new_jobs = []
    for job in jobs:
        key = (str(job.get("Job Title", "")).strip().lower(), str(job.get("Company", "")).strip().lower())
        if key not in existing_keys:
            new_jobs.append(job)
            existing_keys.add(key)
    if new_jobs:
        replace_jobs(new_jobs, user_id)


def _cvs_collection(user_id: str):
    if not user_id:
        raise ValueError("A Firebase user ID is required for CV persistence")
    return _get_database().collection("users").document(user_id).collection("cvs")


def _diagnostic_logs_collection(user_id: str):
    if not user_id:
        raise ValueError("A Firebase user ID is required for diagnostic logs")
    return _get_database().collection("users").document(user_id).collection(DIAGNOSTIC_LOGS_COLLECTION)


def save_diagnostic_log(user_id: str, event: str, details: Dict[str, Any]) -> Dict[str, Any]:
    log_id = uuid.uuid4().hex
    record = {
        "id": log_id,
        "event": event,
        "details": details,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _diagnostic_logs_collection(user_id).document(log_id).set(record)
    return record


def fetch_diagnostic_logs(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    records = [document.to_dict() for document in _diagnostic_logs_collection(user_id).stream()]
    return sorted(records, key=lambda record: str(record.get("created_at", "")), reverse=True)[:limit]


def fetch_all_diagnostic_logs(limit: int = 500) -> List[Dict[str, Any]]:
    records = [document.to_dict() for document in _get_database().collection_group(DIAGNOSTIC_LOGS_COLLECTION).stream()]
    return sorted(records, key=lambda record: str(record.get("created_at", "")), reverse=True)[:limit]


def save_cv(user_id: str, filename: str, content_type: str, content: bytes) -> Dict[str, Any]:
    cv_id = uuid.uuid4().hex
    storage_path = f"users/{user_id}/cvs/{cv_id}/{filename}"
    blob = storage.bucket().blob(storage_path)
    blob.upload_from_string(content, content_type=content_type or "application/octet-stream")
    record = {
        "id": cv_id,
        "name": filename,
        "content_type": content_type or "application/octet-stream",
        "size": len(content),
        "storage_path": storage_path,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _cvs_collection(user_id).document(cv_id).set(record)
    return record


def fetch_cvs(user_id: str) -> List[Dict[str, Any]]:
    records = [document.to_dict() for document in _cvs_collection(user_id).stream()]
    return sorted(records, key=lambda record: str(record.get("created_at", "")), reverse=True)


def download_cv(user_id: str, cv_id: str) -> tuple[Dict[str, Any], bytes]:
    document = _cvs_collection(user_id).document(cv_id).get()
    if not document.exists:
        raise KeyError("CV not found")
    record = document.to_dict() or {}
    content = storage.bucket().blob(str(record["storage_path"])).download_as_bytes()
    return record, content


def delete_cv(user_id: str, cv_id: str) -> None:
    document = _cvs_collection(user_id).document(cv_id)
    snapshot = document.get()
    if not snapshot.exists:
        raise KeyError("CV not found")
    record = snapshot.to_dict() or {}
    storage_path = str(record.get("storage_path") or "")
    if storage_path:
        storage.bucket().blob(storage_path).delete()
    document.delete()


def rename_cv(user_id: str, cv_id: str, new_name: str) -> Dict[str, Any]:
    document = _cvs_collection(user_id).document(cv_id)
    snapshot = document.get()
    if not snapshot.exists:
        raise KeyError("CV not found")
    record = snapshot.to_dict() or {}
    old_name = str(record.get("name") or "")
    old_path = str(record.get("storage_path") or "")
    if old_path:
        prefix = old_path.rsplit("/", 1)[0]
        new_path = f"{prefix}/{new_name}"
        bucket = storage.bucket()
        bucket.copy_blob(bucket.blob(old_path), bucket, new_path)
        bucket.blob(old_path).delete()
        record["storage_path"] = new_path
    record["name"] = new_name
    document.set(record)
    if old_name and old_name != new_name:
        _update_cv_name_in_jobs(user_id, old_name, new_name)
    return record


def _update_cv_name_in_jobs(user_id: str, old_name: str, new_name: str) -> None:
    """Update the Recommended CV field in all jobs that reference the old CV filename."""
    collection = _jobs_collection(user_id)
    for doc in collection.stream():
        data = (doc.to_dict() or {}).get("data") or {}
        if data.get("Recommended CV") == old_name:
            data["Recommended CV"] = new_name
            collection.document(doc.id).set({"data": data})


def save_prompt_preference(
    user_id: str,
    prompt: str,
    job_title: str = "",
    company: str = "",
    interaction_type: str = "tailor",
    response: str = "",
) -> Dict[str, Any]:
    preference_id = uuid.uuid4().hex
    record = {
        "id": preference_id,
        "prompt": prompt.strip(),
        "job_title": job_title.strip(),
        "company": company.strip(),
        "interaction_type": interaction_type,
        "response": response[:4000],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _get_database().collection("users").document(user_id).collection("prompt_preferences").document(preference_id).set(record)
    return record


def fetch_prompt_preferences(user_id: str, limit: int = 12) -> List[Dict[str, Any]]:
    collection = _get_database().collection("users").document(user_id).collection("prompt_preferences")
    records = [document.to_dict() for document in collection.stream()]
    return sorted(records, key=lambda record: str(record.get("created_at", "")), reverse=True)[:limit]


def save_match_feedback(
    user_id: str,
    job_title: str,
    company: str,
    feedback_type: str,
    notes: str = "",
    fit_score: str = "",
) -> Dict[str, Any]:
    feedback_id = uuid.uuid4().hex
    record = {
        "id": feedback_id,
        "job_title": job_title.strip(),
        "company": company.strip(),
        "feedback_type": feedback_type,
        "notes": notes.strip()[:1000],
        "fit_score": fit_score.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _get_database().collection("users").document(user_id).collection("match_feedback").document(feedback_id).set(record)
    return record


def fetch_role_preferences(user_id: str) -> Dict[str, Any]:
    document = _get_database().collection("users").document(user_id).collection("preferences").document("roles").get()
    data = document.to_dict() or {}
    return {
        "target_roles": data.get("target_roles", []),
        "excluded_roles": data.get("excluded_roles", []),
        "target_location": data.get("target_location", ""),
        "max_posting_age_days": int(data.get("max_posting_age_days", 7)),
    }


def save_role_preferences(user_id: str, target_roles: List[str], excluded_roles: List[str], target_location: str = "", max_posting_age_days: int = 7) -> Dict[str, Any]:
    record = {
        "target_roles": target_roles,
        "excluded_roles": excluded_roles,
        "target_location": target_location.strip(),
        "max_posting_age_days": max(1, int(max_posting_age_days)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _get_database().collection("users").document(user_id).collection("preferences").document("roles").set(record)
    return record