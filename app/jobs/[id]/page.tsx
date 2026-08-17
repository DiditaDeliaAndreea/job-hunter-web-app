'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, ExternalLink, Briefcase, FileText, Sparkles, Pencil, Check, X, Trash2 } from 'lucide-react';
import { getUploadedCv } from '../../../utils/browserStorage';
import mammoth from 'mammoth';
import { apiFetch } from '../../../lib/api';
import BackButton from '../../back-button';

interface JobRecord {
  [key: string]: string | undefined;
}

function formatPostedDate(value: unknown): string {
  const rawValue = String(value || '').trim();
  if (!rawValue || rawValue.toLowerCase() === 'not specified') return 'Not specified';
  if (/\b(ago|today|yesterday)\b/i.test(rawValue)) return rawValue;

  const postedAt = new Date(rawValue);
  if (Number.isNaN(postedAt.getTime())) return rawValue;

  const elapsedHours = Math.max(0, (Date.now() - postedAt.getTime()) / (1000 * 60 * 60));
  if (elapsedHours < 1) {
    const minutes = Math.max(1, Math.floor(elapsedHours * 60));
    return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'} ago`;
  }
  if (elapsedHours < 24) {
    const hours = Math.floor(elapsedHours);
    return `${hours} ${hours === 1 ? 'hour' : 'hours'} ago`;
  }

  const days = Math.floor(elapsedHours / 24);
  return days === 0 ? 'Today' : `${days} ${days === 1 ? 'day' : 'days'} ago`;
}

function getPreferredJobUrl(job: JobRecord): string | null {
  const officialUrl = String(job['Official Listing URL'] || '').trim();
  const officialVerified = String(job['Official Listing Verified'] || '').toLowerCase() === 'yes';
  if (officialVerified && /^https?:\/\/\S+$/i.test(officialUrl)) return officialUrl;

  const sourceUrl = String(job.URL || '').trim();
  return /^https?:\/\/\S+$/i.test(sourceUrl) ? sourceUrl : null;
}

const ATS_STOP_WORDS = new Set([
  'about', 'after', 'also', 'with', 'from', 'have', 'into', 'their', 'there', 'these', 'those',
  'this', 'that', 'will', 'your', 'they', 'them', 'were', 'when', 'where', 'which', 'while',
  'work', 'working', 'role', 'roles', 'team', 'teams', 'using', 'used', 'years', 'must', 'should',
]);

function getComparableWords(value: string): Set<string> {
  return new Set(
    value
      .toLowerCase()
      .replace(/<[^>]*>/g, ' ')
      .match(/[a-z0-9][a-z0-9+#./-]{2,}/g) || []
  );
}

function renderHighlightedTailoredCv(tailoredCv: string, originalCv: string, jobDescription: string) {
  const originalWords = getComparableWords(originalCv);
  const jobKeywords = [...getComparableWords(jobDescription)].filter(
    (word) => !ATS_STOP_WORDS.has(word) && word.length >= 4
  );
  const addedKeywords = new Set(jobKeywords.filter((word) => !originalWords.has(word)));

  return tailoredCv.split(/(\s+)/).map((part, index) => {
    const normalizedPart = part.toLowerCase().replace(/[^a-z0-9+#./-]/g, '');
    if (!normalizedPart || !addedKeywords.has(normalizedPart)) {
      return <span key={`${part}-${index}`}>{part}</span>;
    }
    return (
      <mark key={`${part}-${index}`} className="rounded bg-green-200 px-0.5 text-green-950" title="ATS keyword added from the job description">
        {part}
      </mark>
    );
  });
}

export default function JobDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter();
  const [job, setJob] = useState<JobRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [recommendedCvUrl, setRecommendedCvUrl] = useState<string | null>(null);
  const [recommendedCvHtml, setRecommendedCvHtml] = useState<string | null>(null);
  const [recommendedCvFile, setRecommendedCvFile] = useState<File | null>(null);
  const [tailoredCv, setTailoredCv] = useState('');
  const [generatingTailoredCv, setGeneratingTailoredCv] = useState(false);
  const [tailoredCvMessage, setTailoredCvMessage] = useState('');
  const [cvPrompt, setCvPrompt] = useState('');
  const [cvChatAnswer, setCvChatAnswer] = useState('');
  const [askingCvQuestion, setAskingCvQuestion] = useState(false);
  const [editingUrl, setEditingUrl] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [urlMessage, setUrlMessage] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState('');

  useEffect(() => {
    let active = true;

    const loadJob = async () => {
      try {
        const resolvedParams = await params;
        const jobIndex = Number(resolvedParams.id);
        const response = await apiFetch('/api/jobs');
        if (!response.ok) {
          throw new Error(`Jobs API request failed: ${response.status}`);
        }
        const data = await response.json();

        if (!response.ok || !Array.isArray(data.jobs)) {
          throw new Error('Could not load job matches.');
        }
        if (!Number.isInteger(jobIndex) || !data.jobs[jobIndex]) {
          throw new Error('This job match could not be found.');
        }

        if (active) setJob(data.jobs[jobIndex]);
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : 'Could not load this job match.');
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    loadJob();
    return () => {
      active = false;
    };
  }, [params]);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    const recommendedCv = job?.['Recommended CV'];
    setRecommendedCvUrl(null);
    setRecommendedCvHtml(null);
    setRecommendedCvFile(null);

    if (!recommendedCv || recommendedCv === 'Not specified') {
      setRecommendedCvUrl(null);
      setRecommendedCvHtml(null);
      return () => undefined;
    }

    const processFile = async (file: File) => {
      if (!active) return;
      setRecommendedCvFile(file);
      if (file.name.toLowerCase().endsWith('.docx')) {
        const result = await mammoth.convertToHtml({ arrayBuffer: await file.arrayBuffer() });
        if (active) setRecommendedCvHtml(result.value);
        return;
      }
      objectUrl = URL.createObjectURL(file);
      if (active) setRecommendedCvUrl(objectUrl);
    };

    const loadCv = async () => {
      // Try IndexedDB first (fastest, works offline)
      let file = await getUploadedCv(recommendedCv).catch(() => null);

      // Fall back to backend (Firebase Storage) when not cached locally
      if (!file) {
        try {
          const listResponse = await apiFetch('/api/cvs');
          if (listResponse.ok) {
            const { cvs } = await listResponse.json() as { cvs: { id: string; name: string }[] };
            const match = cvs.find((cv) => cv.name === recommendedCv);
            if (match) {
              const contentResponse = await apiFetch(`/api/cvs/${match.id}/content`);
              if (contentResponse.ok) {
                const blob = await contentResponse.blob();
                file = new File([blob], recommendedCv, { type: blob.type });
              }
            }
          }
        } catch {
          // backend unavailable — file stays null
        }
      }

      if (!active || !file) return;
      await processFile(file);
    };

    void loadCv().catch(() => {
      if (active) {
        setRecommendedCvUrl(null);
        setRecommendedCvHtml(null);
      }
    });

    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [job]);

  if (loading) {
    return <main className="min-h-screen w-full px-4 py-8 text-gray-600 md:px-8">Loading job details...</main>;
  }

  if (error || !job) {
    return (
      <main className="min-h-screen w-full px-4 py-8 md:px-8">
        <BackButton label="Back to matches" />
        <div className="mt-10 rounded-xl border border-red-200 bg-red-50 p-6 text-red-800">
          {error || 'Job match not found.'}
        </div>
      </main>
    );
  }

  const url = getPreferredJobUrl(job);
  const officialVerified = String(job['Official Listing Verified'] || '').toLowerCase() === 'yes';
  const originalUrl = /^https?:\/\/\S+$/i.test(String(job['Original Listing URL'] || '').trim())
    ? String(job['Original Listing URL']).trim()
    : null;

  const startUrlEdit = () => {
    setUrlInput(url || '');
    setUrlMessage('');
    setEditingUrl(true);
  };

  const updateAppliedStatus = async () => {
    if (!job) return;
    setActionLoading(true);
    setActionMessage('');
    const formData = new FormData();
    formData.append('job_title', job['Job Title'] || '');
    formData.append('company', job.Company || '');
    formData.append('applied', String(job.Applied !== 'Yes'));
    try {
      const response = await apiFetch('/api/jobs/applied', { method: 'POST', body: formData });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || 'Could not update application status.');
      setJob((current) => current ? { ...current, Applied: data.applied ? 'Yes' : 'No' } : current);
      setActionMessage(data.applied ? 'Marked as applied.' : 'Marked as not applied.');
    } catch (actionError) {
      setActionMessage(actionError instanceof Error ? actionError.message : 'Could not update application status.');
    } finally {
      setActionLoading(false);
    }
  };

  const updateVerificationStatus = async () => {
    if (!job) return;
    setActionLoading(true);
    setActionMessage('');
    const nextStatus = job['Verification Status'] === 'Active' ? 'Expired' : 'Active';
    const formData = new FormData();
    formData.append('job_title', job['Job Title'] || '');
    formData.append('company', job.Company || '');
    formData.append('status', nextStatus);
    try {
      const response = await apiFetch('/api/jobs/status', { method: 'POST', body: formData });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || 'Could not update job status.');
      setJob((current) => current ? { ...current, 'Verification Status': data.status } : current);
      setActionMessage(`Marked as ${nextStatus.toLowerCase()}.`);
    } catch (actionError) {
      setActionMessage(actionError instanceof Error ? actionError.message : 'Could not update job status.');
    } finally {
      setActionLoading(false);
    }
  };

  const deleteJob = async () => {
    if (!job || !window.confirm(`Delete ${job['Job Title']} at ${job.Company}?`)) return;
    setActionLoading(true);
    const formData = new FormData();
    formData.append('job_title', job['Job Title'] || '');
    formData.append('company', job.Company || '');
    try {
      const response = await apiFetch('/api/jobs/dismiss', { method: 'POST', body: formData });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || 'Could not delete this job.');
      router.push('/open-jobs');
    } catch (actionError) {
      setActionMessage(actionError instanceof Error ? actionError.message : 'Could not delete this job.');
      setActionLoading(false);
    }
  };

  const generateTailoredCv = async () => {
    if (!job || !recommendedCvFile) {
      setTailoredCvMessage('The recommended CV is not available in browser storage.');
      return;
    }

    setGeneratingTailoredCv(true);
    setTailoredCvMessage('Preparing a CV matched to this job...');
    try {
      const formData = new FormData();
      formData.append('cv_file', recommendedCvFile);
      formData.append('job_title', job['Job Title'] || '');
      formData.append('company', job.Company || '');
      formData.append('job_description', job['Job Description'] || '');
      formData.append('user_prompt', cvPrompt);
      const response = await apiFetch('/api/jobs/tailor-cv', { method: 'POST', body: formData });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || 'Could not generate the tailored CV.');
      setTailoredCv(data.tailored_cv || '');
      setTailoredCvMessage('Your tailored CV is ready. Review every detail before using it.');
    } catch (generationError) {
      setTailoredCvMessage(generationError instanceof Error ? generationError.message : 'Could not generate the tailored CV.');
    } finally {
      setGeneratingTailoredCv(false);
    }
  };

  const saveUrl = async () => {
    if (!job || !urlInput.trim()) {
      setUrlMessage('Enter a valid listing URL.');
      return;
    }

    const formData = new FormData();
    formData.append('job_title', job['Job Title'] || '');
    formData.append('company', job.Company || '');
    formData.append('url', urlInput.trim());

    try {
      const response = await apiFetch('/api/jobs/update-url', {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || 'Could not update the URL.');

      setJob((currentJob) => currentJob ? {
        ...currentJob,
        URL: data.url,
        'Official Listing URL': data.url,
        'Official Listing Verified': 'Yes',
        'Listing Source': 'User-provided preferred listing',
        'URL Check Status': 'User updated URL; not automatically checked',
      } : currentJob);
      setEditingUrl(false);
      setUrlMessage('Preferred URL updated. Refresh the listings page to update its View link.');
    } catch (saveError) {
      setUrlMessage(saveError instanceof Error ? saveError.message : 'Could not update the URL.');
    }
  };

  const askCvQuestion = async () => {
    if (!job || !recommendedCvFile || !cvPrompt.trim()) return;
    setAskingCvQuestion(true);
    setCvChatAnswer('');
    try {
      const formData = new FormData();
      formData.append('cv_file', recommendedCvFile);
      formData.append('job_title', job['Job Title'] || '');
      formData.append('company', job.Company || '');
      formData.append('job_description', job['Job Description'] || '');
      formData.append('user_prompt', cvPrompt);
      const response = await apiFetch('/api/jobs/tailor-cv/chat', { method: 'POST', body: formData });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || 'Could not answer the tailoring question.');
      setCvChatAnswer(data.answer || 'No answer was returned.');
    } catch (chatError) {
      setCvChatAnswer(chatError instanceof Error ? chatError.message : 'Could not answer the tailoring question.');
    } finally {
      setAskingCvQuestion(false);
    }
  };

  return (
    <main className="min-h-screen w-full px-4 py-6 md:px-8 md:py-8">
      <BackButton label="Back to matches" />

      <header className="mt-8 border-b border-gray-200 pb-6">
        <div className="flex items-start gap-3">
          <Briefcase className="mt-1 h-7 w-7 shrink-0 text-blue-600" />
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-gray-900">{job['Job Title']}</h1>
            <p className="mt-2 text-lg text-gray-600">{job.Company} · {job.Location}</p>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-3 text-sm text-gray-700">
          <span className="rounded-full bg-blue-50 px-3 py-1">Posted: {formatPostedDate(job['Posted Date'])}</span>
          <span className="rounded-full bg-blue-50 px-3 py-1">{job['Working Type'] || 'Not specified'}</span>
          <span className="rounded-full bg-blue-50 px-3 py-1">Salary: {job.Salary || 'Not specified'}</span>
          <span className="rounded-full bg-green-50 px-3 py-1">Match: {job['Fit Score (%)'] || 'Not specified'}</span>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-4">
          <button type="button" onClick={() => void updateAppliedStatus()} disabled={actionLoading} className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50">
            <Check className="h-4 w-4" /> {job.Applied === 'Yes' ? 'Mark not applied' : 'Mark as applied'}
          </button>
          <button type="button" onClick={() => void updateVerificationStatus()} disabled={actionLoading} className="inline-flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50">
            {job['Verification Status'] === 'Active' ? 'Mark expired' : 'Mark active'}
          </button>
          <button type="button" onClick={() => void deleteJob()} disabled={actionLoading} className="inline-flex items-center gap-2 rounded-md border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50">
            <Trash2 className="h-4 w-4" /> Delete
          </button>
          {actionMessage && <span className="text-sm text-gray-600">{actionMessage}</span>}
        </div>
      </header>

      <div className="grid gap-6 py-8 lg:grid-cols-1 lg:items-start">
        <section className="order-2 rounded-xl border border-gray-200 bg-white p-6 shadow-sm lg:order-1">
          <div className="mb-3 flex items-center gap-2">
            <FileText className="h-5 w-5 text-blue-600" />
            <h2 className="text-xl font-semibold text-gray-900">Job description</h2>
          </div>
          <p className="whitespace-pre-wrap leading-7 text-gray-700">{job['Job Description'] || 'No job description was provided yet.'}</p>
        </section>

        <div className="order-1 space-y-6 lg:order-2">
          <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div className="mb-3 flex items-center gap-2">
              <FileText className="h-5 w-5 text-blue-600" />
              <h2 className="text-xl font-semibold text-gray-900">Why this job matches</h2>
            </div>
            <p className="whitespace-pre-wrap leading-7 text-gray-700">{job['Match Reasons'] || 'No match explanation was provided.'}</p>
          </section>

          {job['Missing Requirements'] && job['Missing Requirements'] !== 'None identified' && (
            <section className="rounded-xl border border-amber-100 bg-amber-50 p-6">
              <div className="mb-3 flex items-center gap-2">
                <FileText className="h-5 w-5 text-amber-600" />
                <h2 className="text-xl font-semibold text-gray-900">Missing requirements</h2>
              </div>
              <p className="whitespace-pre-wrap leading-7 text-gray-700">{job['Missing Requirements']}</p>
            </section>
          )}

          <section className="rounded-xl border border-indigo-100 bg-indigo-50 p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-indigo-700" />
                  <h2 className="text-xl font-semibold text-gray-900">CV workspace</h2>
                </div>
                <p className="text-sm text-gray-700">Compare your recommended CV with a version tailored to this job.</p>
              </div>
              <button
                type="button"
                onClick={generateTailoredCv}
                disabled={generatingTailoredCv || !recommendedCvFile}
                className="inline-flex items-center gap-2 rounded-md bg-indigo-700 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Sparkles className="h-4 w-4" />
                {generatingTailoredCv ? 'Preparing...' : 'Tailor this CV'}
              </button>
            </div>
            {tailoredCvMessage && <p className="mb-4 text-sm text-indigo-900">{tailoredCvMessage}</p>}
            <div className="mb-4 rounded-lg border border-indigo-200 bg-white p-4">
              <label htmlFor="cv-tailoring-prompt" className="mb-2 block text-sm font-semibold text-gray-900">Tell us how to tailor your CV</label>
              <textarea
                id="cv-tailoring-prompt"
                value={cvPrompt}
                onChange={(event) => setCvPrompt(event.target.value)}
                rows={3}
                placeholder="For example: emphasize my incident management experience and keep the original section names."
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-800 focus:border-indigo-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => void askCvQuestion()}
                disabled={askingCvQuestion || !recommendedCvFile || !cvPrompt.trim()}
                className="mt-3 rounded-md border border-indigo-300 px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {askingCvQuestion ? 'Thinking...' : 'Get advice'}
              </button>
              <p className="mt-2 text-xs text-gray-500">Every prompt is saved automatically and guides future tailoring requests for your account.</p>
              {cvChatAnswer && <div className="mt-3 whitespace-pre-wrap rounded-md bg-indigo-50 p-3 text-sm leading-6 text-indigo-950">{cvChatAnswer}</div>}
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-blue-200 bg-white p-5">
                <h3 className="mb-3 font-semibold text-gray-900">Recommended CV</h3>
                <p className="mb-3 text-sm text-gray-500">{job['Recommended CV'] || 'Not specified'}</p>
                {recommendedCvHtml ? (
                  <div className="max-h-[65vh] overflow-y-auto text-sm text-gray-800 [&_h1]:mb-4 [&_h1]:text-2xl [&_h2]:mb-3 [&_h2]:mt-5 [&_li]:ml-5 [&_li]:list-disc [&_p]:mb-3" dangerouslySetInnerHTML={{ __html: recommendedCvHtml }} />
                ) : recommendedCvUrl ? (
                  <iframe src={recommendedCvUrl} title="Recommended CV" className="h-[65vh] w-full rounded border border-gray-200" />
                ) : (
                  <p className="text-sm text-gray-500">{recommendedCvFile ? 'Preview is not available for this file type.' : 'CV not found in storage. Re-upload it from the home page to enable preview and tailoring.'}</p>
                )}
              </div>
              <div className="rounded-lg border border-indigo-200 bg-white p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <h3 className="font-semibold text-gray-900">Tailored CV</h3>
                  <span className="inline-flex items-center gap-2 text-xs text-green-800">
                    <span className="h-3 w-3 rounded-sm bg-green-200" aria-hidden="true" /> Added ATS keywords
                  </span>
                </div>
                {tailoredCv ? (
                  <pre className="max-h-[65vh] overflow-y-auto whitespace-pre-wrap font-sans text-sm leading-6 text-gray-800">{renderHighlightedTailoredCv(tailoredCv, recommendedCvHtml || '', job['Job Description'] || '')}</pre>
                ) : <p className="text-sm text-gray-500">Generate a tailored version to see the suggested wording and keywords here.</p>}
              </div>
            </div>
          </section>

          <section className="border-t border-gray-200 pt-6">
            <h2 className="mb-3 text-lg font-semibold text-gray-900">Job listing</h2>
            <div className="mb-4 space-y-1 text-sm text-gray-600">
              <p>Source: {job['Listing Source'] || 'Not specified'}</p>
              <p>Official employer listing verified: {job['Official Listing Verified'] || 'Not specified'}</p>
              <p>URL status: {job['URL Check Status'] || 'Not checked'}</p>
            </div>
            {url ? (
              <div className="mb-3 flex flex-col items-start gap-2">
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700"
                >
                  {officialVerified ? 'Open official listing' : 'Open original listing'} <ExternalLink className="h-4 w-4" />
                </a>

                {originalUrl && originalUrl !== url && (
                  <a
                    href={originalUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 text-sm font-medium text-blue-700 hover:underline"
                  >
                    View source listing <ExternalLink className="h-4 w-4" />
                  </a>
                )}

                {editingUrl ? (
                  <div className="mt-1 flex w-full flex-wrap items-center gap-2">
                    <input
                      type="url"
                      value={urlInput}
                      onChange={(event) => setUrlInput(event.target.value)}
                      placeholder="https://correct-job-listing-url"
                      className="min-w-0 flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={saveUrl}
                      title="Save preferred URL"
                      className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
                    >
                      <Check className="h-4 w-4" /> Save
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingUrl(false)}
                      title="Cancel URL edit"
                      className="inline-flex items-center gap-1 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                    >
                      <X className="h-4 w-4" /> Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={startUrlEdit}
                    className="inline-flex items-center gap-2 text-sm font-medium text-blue-700 hover:underline"
                  >
                    <Pencil className="h-4 w-4" /> Edit listing URL
                  </button>
                )}
              </div>
            ) : (
              <div className="mb-3 flex flex-col items-start gap-2">
                <p className="text-sm text-gray-500">The original listing URL was not provided.</p>
                {editingUrl ? (
                  <div className="mt-1 flex w-full flex-wrap items-center gap-2">
                    <input
                      type="url"
                      value={urlInput}
                      onChange={(event) => setUrlInput(event.target.value)}
                      placeholder="https://correct-job-listing-url"
                      className="min-w-0 flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={saveUrl}
                      title="Save preferred URL"
                      className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
                    >
                      <Check className="h-4 w-4" /> Save
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingUrl(false)}
                      title="Cancel URL edit"
                      className="inline-flex items-center gap-1 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                    >
                      <X className="h-4 w-4" /> Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={startUrlEdit}
                    className="inline-flex items-center gap-2 text-sm font-medium text-blue-700 hover:underline"
                  >
                    <Pencil className="h-4 w-4" /> Edit listing URL
                  </button>
                )}
              </div>
            )}
            {urlMessage && <p className="mb-4 text-sm text-blue-700">{urlMessage}</p>}
          </section>
        </div>

      </div>
    </main>
  );
}
