from utils.hybrid_search import search_jobs
import api.index as api
import json
import pytest


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