from utils.hybrid_search import search_jobs
import api.index as api
import json
import pytest
from datetime import date, timedelta


def test_hybrid_search_matches_exact_terms_without_embeddings(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    jobs = [
        {"Job Title": "Java Architect", "Company": "One", "Job Description": "Architecture"},
        {"Job Title": "Python Technical Manager", "Company": "Two", "Job Description": "Python platform leadership"},
    ]

    results = search_jobs(jobs, "Python", limit=10)

    assert results[0]["Company"] == "Two"
    assert len(results) == 1


def test_hybrid_search_returns_jobs_in_original_order_without_query():
    jobs = [{"Job Title": "First"}, {"Job Title": "Second"}]

    assert search_jobs(jobs, "", limit=10) == jobs


def test_normalize_job_structures_extraction_fields():
    job = {
        "Job Title": "Technical Manager",
        "Company": "ExampleCo",
        "Original Listing URL": "https://example.com/technical-manager",
        "Job Description": "A detailed technical management role covering platform leadership, delivery, stakeholder management, operational planning, incident response, and team development. " * 5,
        "extracted_skills": ["Python", "AWS"],
        "required_experience_years": "5+ years",
        "seniority_level": "Manager",
        "must_have_requirements": ["People leadership"],
    }

    normalized = api.normalize_job(job)

    assert normalized is not None
    assert normalized["Extracted Skills"] == "Python; AWS"
    assert normalized["Seniority Level"] == "Manager"
    assert "Technical Manager" in normalized["Embedding Text"]


@pytest.mark.asyncio
async def test_reranker_orders_jobs_by_match_score(monkeypatch):
    async def fake_call(*args, **kwargs):
        return json.dumps([
            {"job_index": 0, "match_score": "65%", "why_match": "Partial", "skill_gaps": ["AWS"]},
            {"job_index": 1, "match_score": 92, "why_match": "Strong", "skill_gaps": []},
        ])

    monkeypatch.setattr(api, "call_gemini_with_retry", fake_call)
    jobs = [
        {"Job Title": "First", "Job Description": "First description"},
        {"Job Title": "Second", "Job Description": "Second description"},
    ]

    results = await api.rerank_jobs_with_gemini("candidate profile", jobs)

    assert results[0]["Job Title"] == "Second"
    assert results[0]["Fit Score (%)"] == "92%"


def test_stale_jobs_are_marked_expired_but_user_overrides_are_preserved():
    stale_date = (date.today() - timedelta(days=22)).isoformat()
    jobs = [
        {"Job Title": "Stale", "First Seen Date": stale_date, "Status": "Active"},
        {"Job Title": "Override", "First Seen Date": stale_date, "User Status Override": "Yes", "Status": "Active"},
    ]

    changed = api.mark_stale_jobs_expired(jobs, stale_after_days=21)

    assert changed is True
    assert jobs[0]["Verification Status"] == "Expired"
    assert jobs[1]["Status"] == "Active"


def test_irishjobs_unavailable_page_is_detected_as_expired():
    page_text = (
        "#### Oh no, this job is no longer available. "
        "But don't worry! We've searched for similar jobs for you."
    )

    assert api.is_expired_listing_text(page_text) is True


def test_active_linkedin_listing_overrides_expired_aggregator(monkeypatch):
    jobs = [{
        "Job Title": "Technical Manager",
        "Company": "ExampleCo",
        "Verification Status": "Not verified",
        "Verification Notes": "Not specified",
        "Original Listing URL": "https://www.irishjobs.ie/job/123",
        "URL": "https://www.irishjobs.ie/job/123",
    }]
    exported = []

    monkeypatch.setattr(api, "import_jobs_from_csv", lambda filename, user_id: jobs)
    monkeypatch.setattr(api, "export_jobs_to_csv", lambda rows, filename, user_id: exported.append(rows))
    monkeypatch.setattr("utils.csv_utils.export_jobs_to_csv", lambda rows, filename, user_id: exported.append(rows))
    monkeypatch.setattr(
        api,
        "_url_is_expired_sync",
        lambda url: "irishjobs.ie" in url,
    )

    api.update_verification_rows([
        {
            "Job Title": "Technical Manager",
            "Company": "ExampleCo",
            "Verification Status": "Active",
            "Official Listing URL": "https://www.linkedin.com/jobs/view/456",
        }
    ], "user-1")

    assert jobs[0]["Verification Status"] == "Active"


def test_expired_linkedin_listing_overrides_active_aggregator(monkeypatch):
    jobs = [{
        "Job Title": "Technical Manager",
        "Company": "ExampleCo",
        "Verification Status": "Not verified",
        "Verification Notes": "Not specified",
        "Original Listing URL": "https://www.linkedin.com/jobs/view/456",
        "URL": "https://www.linkedin.com/jobs/view/456",
    }]
    monkeypatch.setattr(api, "import_jobs_from_csv", lambda filename, user_id: jobs)
    monkeypatch.setattr(api, "export_jobs_to_csv", lambda rows, filename, user_id: None)
    monkeypatch.setattr("utils.csv_utils.export_jobs_to_csv", lambda rows, filename, user_id: None)
    monkeypatch.setattr(api, "_url_is_expired_sync", lambda url: "linkedin.com" in url)

    api.update_verification_rows([
        {
            "Job Title": "Technical Manager",
            "Company": "ExampleCo",
            "Verification Status": "Active",
            "Official Listing URL": "https://www.irishjobs.ie/job/123",
        }
    ], "user-1")

    assert jobs[0]["Verification Status"] == "Expired"