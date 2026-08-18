import json
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api.index as api


def test_technical_manager_search_expands_to_adjacent_management_roles():
    roles = api.build_search_roles(["Technical Manager"], [], [])

    assert "Technical Manager" in roles
    assert "IT Manager" in roles
    assert "Technology Manager" in roles
    assert "Technical Operations Manager" in roles


@pytest.mark.asyncio
async def test_call_gemini_uses_google_search_tool_when_requested(monkeypatch):
    class FakeClient:
        def __init__(self):
            self.last_config = None
            self.last_model = None
            self.last_contents = None

        class models:
            @staticmethod
            def generate_content(model, contents, config=None):
                client = FakeClient.__dict__.get('_current_client')
                client.last_model = model
                client.last_contents = contents
                client.last_config = config
                return SimpleNamespace(text='{"ok": true}')

    fake_client = FakeClient()
    FakeClient._current_client = fake_client
    fake_genai = SimpleNamespace(Client=lambda **kwargs: fake_client if kwargs else fake_client)
    monkeypatch.setitem(sys.modules, 'google.genai', fake_genai)

    result = await api.call_gemini_with_retry('instructions', 'prompt', use_google_search=True)

    assert result == '{"ok": true}'
    assert fake_client.last_model == 'gemini-flash-latest'
    assert fake_client.last_config['tools'] == [{'google_search': {}}]


@pytest.mark.asyncio
async def test_partial_batch_results_are_persisted_before_error(monkeypatch):
    monkeypatch.setattr(api, "TARGET_ROLES", [f"Role {i}" for i in range(1, 13)])
    monkeypatch.setattr(api, "EXCLUDED_ROLES", [])

    calls = {"count": 0}
    persisted = []

    async def fake_call_gemini_with_retry(instructions, prompt, use_google_search=False, max_retries=3, initial_delay=8):
        del instructions, prompt, use_google_search, max_retries, initial_delay
        calls["count"] += 1
        if calls["count"] == 1:
            return json.dumps([
                {
                    "Job Title": "QA Engineer",
                    "Company": "ExampleCo",
                    "Location": "Dublin, Ireland",
                    "Fit Score (%)": "92%",
                    "Match Reasons": "Strong QA background",
                    "Status": "Active",
                        "URL": "https://example.com/job-1",
                        "Original Listing URL": "https://example.com/job-1",
                        "Job Description": "A detailed QA engineering role description covering testing, automation, defect triage, regression coverage, collaboration with software engineers, test planning, documentation, and release validation. " * 5
                }
            ])
        raise HTTPException(status_code=503, detail="503 Service Unavailable")

    def fake_append_jobs_to_csv(jobs, filename="job_matches.csv"):
        persisted.append(list(jobs))
        return str(filename)

    monkeypatch.setattr(api, "call_job_search_model", fake_call_gemini_with_retry)
    monkeypatch.setattr(api, "append_jobs_to_csv", fake_append_jobs_to_csv)

    async def keep_fixture_jobs(jobs):
        return jobs

    monkeypatch.setattr(api, "validate_listing_urls", keep_fixture_jobs)

    result = await api.run_incremental_job_finder("candidate profile")

    assert result[0]["Job Title"] == "QA Engineer"
    assert persisted and persisted[0][0]["Job Title"] == "QA Engineer"
