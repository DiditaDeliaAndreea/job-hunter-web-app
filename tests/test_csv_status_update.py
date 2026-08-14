from utils.csv_utils import update_job_status_in_csv


def test_update_job_status_in_csv_updates_verification_status(tmp_path, monkeypatch):
    csv_path = tmp_path / 'job_matches.csv'
    csv_path.write_text(
        'Job Title,Company,Location,Posted Date,Working Type,Salary,Fit Score (%),Match Reasons,Job Description,Recommended CV,CV Tailoring Recommendation,Status,URL,Listing Source,Official Listing Verified,Official Listing URL,Original Listing URL,URL Check Status,User Dismissed,Applied,Verification Status,Verification Notes,Last Verified\n'
        'Engineer,Acme,Remote,2026-01-01,Remote,100000,80%,Good,Some description,cv.pdf,Tip,Active,https://example.com,Official,Yes,https://example.com,https://example.com,Checked,No,No,Not verified,Not checked,2026-01-01\n',
        encoding='utf-8'
    )

    monkeypatch.setattr('utils.csv_utils.DATA_DIR', tmp_path)

    updated = update_job_status_in_csv('Engineer', 'Acme', 'Active', str(csv_path.name))

    assert updated is True
    rows = csv_path.read_text(encoding='utf-8').strip().splitlines()
    assert 'Active' in rows[1]
