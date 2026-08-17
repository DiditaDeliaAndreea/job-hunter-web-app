'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, BarChart3, BriefcaseBusiness, CheckCircle2, Clock3, RefreshCw, Target } from 'lucide-react';
import { apiFetch } from '../../lib/api';
import { readCachedJobs, writeCachedJobs } from '../../lib/client-cache';
import BackButton from '../back-button';

type Job = Record<string, string | undefined>;

type CountItem = {
  label: string;
  count: number;
};

function countBy(jobs: Job[], field: string, fallback: string): CountItem[] {
  const counts = new Map<string, number>();
  jobs.forEach((job) => {
    const value = String(job[field] || '').trim() || fallback;
    counts.set(value, (counts.get(value) || 0) + 1);
  });
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

function getRoleType(job: Job): string {
  const title = String(job['Job Title'] || '').toLowerCase();
  if (/(quality assurance|qa\b|test engineer|testing|tester|quality expert|quality specialist|quality engineer|software quality)/i.test(title)) {
    return 'QA & Testing';
  }
  if (/(data analyst|data engineer|data operations|data quality|analytics|model operations|modelops|data engineering)/i.test(title)) {
    return 'Data & Analytics';
  }
  if (/(technical support|support engineer|support technician|application support|customer support|service delivery)/i.test(title)) {
    return 'Technical Support';
  }
  if (/(operations|assurance|capacity|business operations|content operations)/i.test(title)) {
    return 'Operations';
  }
  if (/(business analyst|systems analyst|business applications)/i.test(title)) {
    return 'Business & Systems Analysis';
  }
  if (/(engineer|developer|software|automation|prompt)/i.test(title)) {
    return 'Engineering & Development';
  }
  if (/(consultant|product specialist|product management)/i.test(title)) {
    return 'Product & Consulting';
  }
  return 'Other';
}

function StatCard({ label, value, detail, icon: Icon, accent }: {
  label: string;
  value: string;
  detail: string;
  icon: typeof BarChart3;
  accent: string;
}) {
  return (
    <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-gray-500">{label}</p>
          <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900">{value}</p>
          <p className="mt-1 text-sm text-gray-500">{detail}</p>
        </div>
        <div className={`rounded-lg p-3 ${accent}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </article>
  );
}

function Breakdown({ title, items, total }: { title: string; items: CountItem[]; total: number }) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
      <div className="mt-5 space-y-4">
        {items.length === 0 ? (
          <p className="text-sm text-gray-500">No data available.</p>
        ) : items.slice(0, 6).map((item) => {
          const percentage = total > 0 ? Math.round((item.count / total) * 100) : 0;
          return (
            <div key={item.label}>
              <div className="mb-1 flex items-center justify-between gap-4 text-sm">
                <span className="truncate text-gray-700">{item.label}</span>
                <span className="shrink-0 font-semibold text-gray-900">{item.count} <span className="font-normal text-gray-400">({percentage}%)</span></span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-gray-100">
                <div className="h-full rounded-full bg-blue-600" style={{ width: `${percentage}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function StatsPage() {
  const [jobs, setJobs] = useState<Job[]>(() => readCachedJobs<Job>());
  const [loading, setLoading] = useState(() => readCachedJobs<Job>().length === 0);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadJobs = async () => {
    if (jobs.length === 0) setLoading(true);
    setError('');
    try {
      const response = await apiFetch('/api/jobs', { cache: 'no-store' });
      if (!response.ok) throw new Error(`Jobs API request failed: ${response.status}`);
      const data = await response.json();
      const savedJobs = Array.isArray(data.jobs) ? data.jobs as Job[] : [];
      writeCachedJobs(savedJobs);
      setJobs(savedJobs);
      setLastUpdated(new Date());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load saved jobs.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadJobs();
  }, []);

  const stats = useMemo(() => {
    const applied = jobs.filter((job) => job.Applied === 'Yes').length;
    const active = jobs.filter((job) => job['Verification Status'] === 'Active').length;
    const expired = jobs.filter((job) => job['Verification Status'] === 'Expired').length;
    const verified = jobs.filter((job) => ['Active', 'Expired', 'Blocked'].includes(String(job['Verification Status'] || ''))).length;
    const salaryKnown = jobs.filter((job) => {
      const salary = String(job.Salary || '').trim().toLowerCase();
      return salary && salary !== 'not specified';
    }).length;
    const fitScores = jobs
      .map((job) => Number.parseInt(String(job['Fit Score (%)'] || '').replace('%', ''), 10))
      .filter((score) => !Number.isNaN(score));
    const averageFit = fitScores.length ? Math.round(fitScores.reduce((sum, score) => sum + score, 0) / fitScores.length) : 0;

    return {
      applied,
      active,
      expired,
      verified,
      salaryKnown,
      averageFit,
      applicationRate: jobs.length ? Math.round((applied / jobs.length) * 100) : 0,
    };
  }, [jobs]);

  const appliedCompanies = useMemo(
    () => countBy(jobs.filter((job) => job.Applied === 'Yes'), 'Company', 'Unknown company').slice(0, 8),
    [jobs]
  );
  const appliedRoleTypes = useMemo(() => {
    const appliedJobs = jobs.filter((job) => job.Applied === 'Yes');
    const counts = new Map<string, number>();
    appliedJobs.forEach((job) => {
      const roleType = getRoleType(job);
      counts.set(roleType, (counts.get(roleType) || 0) + 1);
    });
    return [...counts.entries()]
      .map(([label, count]) => ({ label, count }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  }, [jobs]);
  const statuses = useMemo(() => countBy(jobs, 'Verification Status', 'Not verified'), [jobs]);
  const workingTypes = useMemo(() => countBy(jobs, 'Working Type', 'Not specified'), [jobs]);

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-6 text-gray-900 md:px-8 lg:px-10">
      <header className="mx-auto mb-8 flex max-w-7xl flex-wrap items-center justify-between gap-4">
        <div>
          <div className="mb-3"><BackButton label="Back to jobs" /></div>
          <h1 className="text-4xl font-bold tracking-tight">Job search stats</h1>
          <p className="mt-2 text-gray-500">A clear view of your saved opportunities and applications.</p>
        </div>
        <button
          type="button"
          onClick={() => void loadJobs()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh stats
        </button>
      </header>

      <div className="mx-auto max-w-7xl">
        {error && <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
        {loading && jobs.length === 0 ? (
          <div className="rounded-xl border border-gray-200 bg-white p-10 text-center text-gray-500">Loading your stats...</div>
        ) : (
          <>
            <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Saved jobs" value={String(jobs.length)} detail={`${stats.verified} listings checked`} icon={BriefcaseBusiness} accent="bg-blue-100 text-blue-700" />
              <StatCard label="Applications" value={String(stats.applied)} detail={`${stats.applicationRate}% of saved jobs`} icon={CheckCircle2} accent="bg-emerald-100 text-emerald-700" />
              <StatCard label="Active opportunities" value={String(stats.active)} detail={`${stats.expired} marked expired`} icon={Target} accent="bg-amber-100 text-amber-700" />
              <StatCard label="Average match" value={`${stats.averageFit}%`} detail={`${stats.salaryKnown} jobs show salary data`} icon={BarChart3} accent="bg-indigo-100 text-indigo-700" />
            </section>

            <section className="mt-6 grid gap-6 lg:grid-cols-2">
              <Breakdown title="Verification status" items={statuses} total={jobs.length} />
              <Breakdown title="Working type" items={workingTypes} total={jobs.length} />
            </section>

            <section className="mt-6">
              <Breakdown title="Applied role types" items={appliedRoleTypes} total={stats.applied} />
            </section>

            <section className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900">Applied by company</h2>
                    <p className="mt-1 text-sm text-gray-500">Where your applications are concentrated.</p>
                  </div>
                  <Clock3 className="h-5 w-5 text-gray-400" />
                </div>
                <div className="mt-5 space-y-3">
                  {appliedCompanies.length === 0 ? (
                    <p className="text-sm text-gray-500">No applications marked yet.</p>
                  ) : appliedCompanies.map((item) => (
                    <div key={item.label} className="flex items-center justify-between border-b border-gray-100 pb-3 text-sm last:border-0 last:pb-0">
                      <span className="truncate pr-4 text-gray-700">{item.label}</span>
                      <span className="font-semibold text-gray-900">{item.count}</span>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <h2 className="text-lg font-semibold text-gray-900">Application progress</h2>
                <div className="mt-5">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-600">Applied</span>
                    <span className="font-semibold text-gray-900">{stats.applicationRate}%</span>
                  </div>
                  <div className="mt-2 h-3 overflow-hidden rounded-full bg-gray-100">
                    <div className="h-full rounded-full bg-emerald-500" style={{ width: `${stats.applicationRate}%` }} />
                  </div>
                  <div className="mt-6 grid grid-cols-2 gap-3 text-center">
                    <div className="rounded-lg bg-emerald-50 p-4">
                      <p className="text-2xl font-bold text-emerald-700">{stats.applied}</p>
                      <p className="mt-1 text-xs font-medium text-emerald-800">Applied</p>
                    </div>
                    <div className="rounded-lg bg-gray-50 p-4">
                      <p className="text-2xl font-bold text-gray-700">{jobs.length - stats.applied}</p>
                      <p className="mt-1 text-xs font-medium text-gray-600">Not applied</p>
                    </div>
                  </div>
                </div>
              </section>
            </section>

            <p className="mt-6 text-right text-xs text-gray-400">
              {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'Not yet updated'}
            </p>
          </>
        )}
      </div>
    </main>
  );
}
