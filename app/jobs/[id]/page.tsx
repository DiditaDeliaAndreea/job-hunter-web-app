'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, ExternalLink, Briefcase, FileText, Sparkles, Pencil, Check, X } from 'lucide-react';
import { getUploadedCv } from '../../../utils/browserStorage';
import mammoth from 'mammoth';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const getApiUrl = (path: string) => `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;

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

export default function JobDetailsPage({ params }: { params: Promise<{ id: string }> }) {
  const [job, setJob] = useState<JobRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [recommendedCvUrl, setRecommendedCvUrl] = useState<string | null>(null);
  const [recommendedCvHtml, setRecommendedCvHtml] = useState<string | null>(null);
  const [editingUrl, setEditingUrl] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [urlMessage, setUrlMessage] = useState('');

  useEffect(() => {
    let active = true;

    const loadJob = async () => {
      try {
        const resolvedParams = await params;
        const jobIndex = Number(resolvedParams.id);
        const response = await fetch(getApiUrl('/api/jobs'));
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

    if (!recommendedCv || recommendedCv === 'Not specified') {
      setRecommendedCvUrl(null);
      setRecommendedCvHtml(null);
      return () => undefined;
    }

    getUploadedCv(recommendedCv)
      .then(async (file) => {
        if (!active || !file) return;

        if (file.name.toLowerCase().endsWith('.docx')) {
          const result = await mammoth.convertToHtml({ arrayBuffer: await file.arrayBuffer() });
          if (active) setRecommendedCvHtml(result.value);
          return;
        }

        objectUrl = URL.createObjectURL(file);
        if (active) setRecommendedCvUrl(objectUrl);
      })
      .catch(() => {
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
        <Link href="/" className="inline-flex items-center gap-2 text-sm text-blue-600 hover:underline">
          <ArrowLeft className="h-4 w-4" /> Back to matches
        </Link>
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
      const response = await fetch(getApiUrl('/api/jobs/update-url'), {
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

  return (
    <main className="min-h-screen w-full px-4 py-6 md:px-8 md:py-8">
      <Link href="/" className="inline-flex items-center gap-2 text-sm font-medium text-blue-600 hover:underline">
        <ArrowLeft className="h-4 w-4" /> Back to matches
      </Link>

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
      </header>

      <div className="grid gap-6 py-8 lg:grid-cols-2 lg:items-start">
        <section className="order-2 rounded-xl border border-gray-200 bg-white p-6 shadow-sm lg:order-1 lg:sticky lg:top-6">
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

          <section className="rounded-xl border border-blue-100 bg-blue-50 p-6">
            <div className="mb-3 flex items-center gap-2">
              <Briefcase className="h-5 w-5 text-blue-700" />
              <h2 className="text-xl font-semibold text-gray-900">Recommended CV</h2>
            </div>
            <p className="font-medium text-blue-900">
              {recommendedCvUrl ? (
                <a
                  href={recommendedCvUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="underline hover:text-blue-700"
                >
                  {job['Recommended CV']}
                </a>
              ) : recommendedCvHtml ? (
                <a href="#cv-preview" className="underline hover:text-blue-700">
                  {job['Recommended CV']}
                </a>
              ) : (
                job['Recommended CV'] || 'Not specified'
              )}
            </p>
            {recommendedCvUrl && <p className="mt-2 text-sm text-blue-800">Open the recommended CV in a new tab</p>}
            {recommendedCvHtml && (
              <div id="cv-preview" className="mt-4 max-h-[70vh] scroll-mt-6 overflow-y-auto rounded-lg border border-blue-200 bg-white p-6 text-left text-gray-800 [&_h1]:mb-4 [&_h1]:text-2xl [&_h2]:mb-3 [&_h2]:mt-5 [&_h2]:text-xl [&_li]:ml-5 [&_li]:list-disc [&_p]:mb-3">
                <div dangerouslySetInnerHTML={{ __html: recommendedCvHtml }} />
              </div>
            )}
          </section>

          <section className="rounded-xl border border-amber-100 bg-amber-50 p-6">
            <div className="mb-3 flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-amber-700" />
              <h2 className="text-xl font-semibold text-gray-900">CV tailoring recommendation</h2>
            </div>
            <p className="whitespace-pre-wrap leading-7 text-gray-700">{job['CV Tailoring Recommendation'] || 'No tailoring recommendation was provided yet.'}</p>
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
