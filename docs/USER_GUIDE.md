# CareerMatch User Guide

CareerMatch helps you turn your CV into a focused job search. It stores your CVs, role preferences, and saved jobs under your signed-in account so you can keep reviewing opportunities without redoing the setup each time.

## 1. Sign in and create an account

1. Open the app in your browser.
2. Create a new account or sign in with your email and password.
3. If you are prompted to confirm authentication, follow the Firebase sign-in flow.

Once signed in, the app loads your account-specific jobs, CVs, and prompt history.

## 2. Upload your CVs

1. Go to My CVs.
2. Click Add CVs.
3. Choose one or more PDF or DOCX files.
4. Wait for the upload to finish.

The app saves your files to Firebase Storage and keeps the metadata tied to your account. You can then:

- preview a CV
- rename it
- remove it
- select it for a job search

## 3. Set your job preferences

Use the Job preferences page to tell the app what kinds of jobs you want.

### Target roles
These are the roles you want to pursue. Add each one as a separate role, such as:

- Frontend Developer
- Product Analyst
- Data Engineer

### Excluded roles
Use this list to filter out jobs you do not want, such as:

- agency work
- internship-only roles
- unrelated senior positions

### Notes
- Press Enter or comma to add a role.
- Click a role pill to remove it.
- Paste comma-separated or newline-separated entries to add multiple roles quickly.

## 4. Start a job search

1. Open the main Find jobs page.
2. Select the CVs you want to include.
3. Confirm your target and excluded roles.
4. Choose whether you want to search using your current preferences.
5. Click Run job search.

The app will run a job search using your selected CVs and role preferences. Once it completes, you will see a clear link to Open jobs where the new matches are available.

## 5. Review matches in Open jobs

The Open jobs page shows your active matches as cards. Each card includes:

- job title
- company
- location
- working type
- match score
- status
- details link
- original listing link when available

Use the details page for a job to:

- read the full description
- review the match rationale
- compare recommendations
- tailor your CV for that role
- mark the job as applied or expired
- dismiss the job if it is no longer relevant

## 6. Inspect the full job details

Open a job from the list to view the individual job record. From there, you can:

- read the full job description
- see why the app thinks it matches your CV
- check the recommended CV
- ask the app to tailor your CV for this specific role
- update the preferred URL if a better listing is available

## 7. Tailor your CV for a specific opportunity

On a job detail page, use the tailoring workspace to:

- ask for a direct update to your CV
- request a shorter or more targeted summary
- ask for role-specific wording
- improve a cover note or application narrative

The app automatically stores non-empty prompts for your account and reuses recent examples as context in later tailoring requests. This helps the app respond in a way that matches your previous preferences without altering your core profile.

## 8. Manage your applications

The app separates jobs into Open jobs and Applied jobs.

### Open jobs
This is your active shortlist. Keep jobs here if they are still relevant or pending.

### Applied jobs
Move jobs here when you have already applied. The applied page gives you a simple view of the positions you have pursued.

From either page you can:

- mark as applied or not applied
- mark active or expired
- remove outdated positions
- jump into the job detail page

## 9. Keep your data private

Your jobs, CVs, and tailoring prompts are tied to your Firebase account. Only the signed-in user can view and manage their own records.

Do not share or commit:

- API keys
- Firebase service-account JSON
- `.env` files
- local credential files

## 10. Common tasks

### Upload a new version of an existing CV

1. Go to My CVs.
2. Add the new file.
3. The app keeps the uploaded record under your account.

### Search for jobs in a different role

1. Update your target and excluded roles in Job preferences.
2. Go back to Find jobs.
3. Run the search again with the relevant CVs selected.

### Revisit a job later

1. Go to Open jobs.
2. Open the card for the job.
3. Review the full details or update the status.

## 11. Troubleshooting

If you run into a problem, check the main troubleshooting guide in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

Common issues include:

- backend not running
- frontend unable to reach the API
- missing Firebase configuration
- CV upload errors
- empty results during a job search

## 12. Recommended workflow

The simplest way to use the app is:

1. Sign in
2. Upload your CVs
3. Define target roles
4. Run a search
5. Review top matches
6. Tailor each strong candidate
7. Mark applied jobs as you go

This keeps the process organized and makes it easier to compare opportunities and follow up on promising roles.
