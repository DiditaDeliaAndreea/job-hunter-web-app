from utils.csv_utils import import_jobs_from_csv, append_jobs_to_csv, normalize_csv_job

# Define the new jobs
new_jobs_list = [
    ("Analytics Engineer", "Jacobs"),
    ("Quality Expert Reviewer - Romanian Speaker", "Teleperformance"),
    ("Technical Support Technician", "Hays"),
    ("Senior QA & Test Manager", "Smartedge Solutions"),
    ("Data Operations Analyst (SQL & Process Improvement)", "Principle"),
    ("Senior Assurance Analyst - Business Operations & Enablement", "AIB"),
    ("Quality Assurance Specialist", "Yuno Energy"),
    ("Data Engineering Tester", "PTSB"),
    ("Senior QA Analyst - FRS", "Information Services Corporation (ISC)"),
    ("Specialist, Product Management - AI", "Mastercard"),
    ("Test SME", "Korn Ferry"),
    ("QA Analyst", "Cluid"),
    ("QA Engineer", "CarTrawler"),
    ("QA Engineer, Associate (DUB)", "Alchelyst"),
    ("Data Analyst", "QuotoCraft"),
    ("Staff Product Engineer", "Fin"),
    ("Junior Software Engineer, Elixir", "Telnyx"),
    ("Model Operations (ModelOps) Developer", "PTSB"),
    ("Tester / QA Engineer", "Jobgether"),
    ("Quality Assurance Specialist", "Deciphex"),
    ("Quality Assurance Engineer", "Zylo Talent"),
    ("Data Engineer - Join a New Quant Data Engineering Team", "Saragossa"),
    ("AI Agentic Prompt Engineer", "DocuSign"),
    ("Data Analyst", "Hertz"),
    ("Build the Future of AI with Us - Dublin (Hybrid)", "Dun & Bradstreet"),
    ("Product Specialist - SME Third-Party & Partnership Operations", "Mastercard"),
    ("Data Quality Senior Analyst", "Brightwater Recruitment"),
    ("QA Engineer", "Elwood Roberts"),
    ("Content Operations QA Analyst", "Jobgether"),
    ("Quality Assurance Specialist - Data", "Archer Recruitment"),
    ("CSV Engineer", "QCS Staffing"),
    ("Specialist Business Analyst (Data, Analytics & Digital Automation)", "Amgen"),
    ("Senior Business Applications Manager", "Foxit"),
    ("Senior QA Analyst (Financial Markets Experience)", "Engage People Recruitment"),
    ("Senior Engineer QA, PC Apps", "Dolby Laboratories"),
    ("Senior Analyst - Capacity Funding & Delivery", "EirGrid"),
    ("Role not identified in confirmation", "Fuze Health"),
    ("Role not identified in confirmation", "Reperio Human Capital"),
]

# Read existing jobs first
existing_jobs = import_jobs_from_csv()
existing_keys = set((job.get("Job Title", "").lower().strip(), job.get("Company", "").lower().strip()) for job in existing_jobs)

added_count = 0
jobs_to_append = []

# Prepare each job
for title, company in new_jobs_list:
    # Build dictionary
    job_dict = {
        "Job Title": title,
        "Company": company,
        "Applied": "Yes",
        "Verification Status": "Not verified",
        "User Status Override": "No",
        "User Dismissed": "No"
    }
    # normalize using normalize_csv_job
    normalized_job = normalize_csv_job(job_dict)

    # Double check key
    key = (normalized_job.get("Job Title", "").lower().strip(), normalized_job.get("Company", "").lower().strip())
    if key not in existing_keys:
        jobs_to_append.append(normalized_job)
        existing_keys.add(key)
        added_count += 1
    else:
        print(f"Skipping duplicate: {title} - {company}")

if jobs_to_append:
    append_jobs_to_csv(jobs_to_append)
    print(f"Added {len(jobs_to_append)} new unique jobs.")
else:
    print("No new unique jobs added.")

# Query the updated CSV
updated_jobs = import_jobs_from_csv()
print(f"New total row count in data/job_matches.csv is: {len(updated_jobs)}")

print("\nNewly added jobs' details:")
for job in jobs_to_append:
    print(f"- {job.get('Job Title')} - {job.get('Company')} (Applied: {job.get('Applied')})")
