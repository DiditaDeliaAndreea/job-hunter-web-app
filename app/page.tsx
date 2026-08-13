'use client';

import { useState, useRef, useEffect } from 'react';
import * as XLSX from 'xlsx';
import { Upload, FileDown, Loader2, Briefcase, MapPin, X, RefreshCw, Filter, Trash2 } from 'lucide-react';
import { saveUploadedCvs } from '../utils/browserStorage';

const ROLE_PREFERENCES_STORAGE_KEY = 'careermatch-role-preferences';

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

function getPostedAgeDays(value: unknown): number | null {
  const rawValue = String(value || '').trim();
  if (!rawValue || rawValue.toLowerCase() === 'not specified') return null;

  const relativeMatch = rawValue.match(/(\d+)\s+(minute|hour|day|week)s?\s+ago/i);
  if (relativeMatch) {
    const amount = Number(relativeMatch[1]);
    const unit = relativeMatch[2].toLowerCase();
    if (unit === 'minute' || unit === 'hour') return 0;
    if (unit === 'week') return amount * 7;
    return amount;
  }

  const postedAt = new Date(rawValue);
  if (Number.isNaN(postedAt.getTime())) return null;
  return Math.max(0, (Date.now() - postedAt.getTime()) / (1000 * 60 * 60 * 24));
}

function getPreferredJobUrl(job: Record<string, any>): string | null {
  const officialUrl = String(job['Official Listing URL'] || '').trim();
  const officialVerified = String(job['Official Listing Verified'] || '').toLowerCase() === 'yes';
  if (officialVerified && /^https?:\/\/\S+$/i.test(officialUrl)) return officialUrl;

  const sourceUrl = String(job.URL || '').trim();
  return /^https?:\/\/\S+$/i.test(sourceUrl) ? sourceUrl : null;
}

export default function Home() {
  const [files, setFiles] = useState<File[]>([]);
  const [targetRoles, setTargetRoles] = useState('');
  const [excludedRoles, setExcludedRoles] = useState('');
  const [reuseCvAnalysis, setReuseCvAnalysis] = useState(true);
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<any[]>([]);
  const [jobFilter, setJobFilter] = useState('');
  const [workingTypeFilter, setWorkingTypeFilter] = useState('All');
  const [minimumScore, setMinimumScore] = useState('0');
  const [salaryFilter, setSalaryFilter] = useState('All');
  const [postedDateFilter, setPostedDateFilter] = useState('All');
  const [verifyingJobs, setVerifyingJobs] = useState(false);
  const [verificationProgress, setVerificationProgress] = useState(0);
  const [verificationMessage, setVerificationMessage] = useState('');
  const [verificationLogs, setVerificationLogs] = useState<string[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [searchMessage, setSearchMessage] = useState('');
  const [progress, setProgress] = useState(0);
  const [progressLabel, setProgressLabel] = useState('');
  const [liveLogs, setLiveLogs] = useState<string[]>([]);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load jobs on mount
  useEffect(() => {
    fetchJobs();

    const savedPreferences = window.localStorage.getItem(ROLE_PREFERENCES_STORAGE_KEY);
    if (savedPreferences) {
      try {
        const preferences = JSON.parse(savedPreferences);
        setTargetRoles(typeof preferences.targetRoles === 'string' ? preferences.targetRoles : '');
        setExcludedRoles(typeof preferences.excludedRoles === 'string' ? preferences.excludedRoles : '');
      } catch {
        window.localStorage.removeItem(ROLE_PREFERENCES_STORAGE_KEY);
      }
    }
  }, []);

  // Fetch jobs from CSV
  const fetchJobs = async (updateMessage = true) => {
    try {
      const response = await fetch('http://localhost:8000/api/jobs', { cache: 'no-store' });
      const data = await response.json();
      const csvJobs = data.jobs || [];
      setJobs(csvJobs);

      if (updateMessage && csvJobs.length > 0) {
        setSearchMessage(`Loaded ${data.total} jobs from previous search`);
      } else if (updateMessage) {
        setSearchMessage('No saved job matches in CSV yet.');
      }
    } catch (error) {
      console.error('Error fetching jobs:', error);
    }
  };

  // Core file validation and state update
  const addFiles = (selectedFiles: File[]) => {
    const validFiles = selectedFiles.filter((selectedFile) =>
      selectedFile.name.toLowerCase().endsWith('.pdf') || selectedFile.name.toLowerCase().endsWith('.docx')
    );
    if (validFiles.length !== selectedFiles.length) {
      alert('Only PDF and DOCX CV files are supported.');
    }
    setFiles((currentFiles) => {
      const existingNames = new Set(currentFiles.map((selectedFile) => selectedFile.name));
      return [...currentFiles, ...validFiles.filter((selectedFile) => !existingNames.has(selectedFile.name))];
    });
    void saveUploadedCvs(validFiles);
  };

  // 1. Handle Click Selection
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    addFiles(Array.from(e.target.files || []));
    e.target.value = '';
  };

  // 2. Handle Drag Events
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
  };

  // 3. Handle Drop Event
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    addFiles(Array.from(e.dataTransfer.files || []));
  };

  // Clear selected file
  const removeFile = (fileName: string) => {
    setFiles((currentFiles) => currentFiles.filter((selectedFile) => selectedFile.name !== fileName));
  };

  const saveRolePreferences = () => {
    window.localStorage.setItem(
      ROLE_PREFERENCES_STORAGE_KEY,
      JSON.stringify({ targetRoles, excludedRoles })
    );
    setSearchMessage('Role preferences saved for future searches.');
  };

  const clearSavedRolePreferences = () => {
    window.localStorage.removeItem(ROLE_PREFERENCES_STORAGE_KEY);
    setTargetRoles('');
    setExcludedRoles('');
    setSearchMessage('Saved role preferences cleared. Default roles will be used.');
  };

  const dismissJob = async (job: any) => {
    const formData = new FormData();
    formData.append('job_title', job['Job Title'] || '');
    formData.append('company', job.Company || '');

    try {
      const response = await fetch('http://localhost:8000/api/jobs/dismiss', {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) throw new Error('Could not remove this job.');
      setJobs((currentJobs) => currentJobs.filter((currentJob) =>
        currentJob['Job Title'] !== job['Job Title'] || currentJob.Company !== job.Company
      ));
    } catch (error) {
      console.error('Error dismissing job:', error);
      alert('Could not remove this job. Please try again.');
    }
  };

  const updateApplied = async (job: any, applied: boolean) => {
    const formData = new FormData();
    formData.append('job_title', job['Job Title'] || '');
    formData.append('company', job.Company || '');
    formData.append('applied', String(applied));

    try {
      const response = await fetch('http://localhost:8000/api/jobs/applied', {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) throw new Error('Could not update application status.');
      setJobs((currentJobs) => currentJobs.map((currentJob) =>
        currentJob['Job Title'] === job['Job Title'] && currentJob.Company === job.Company
          ? { ...currentJob, Applied: applied ? 'Yes' : 'No' }
          : currentJob
      ));
    } catch (error) {
      console.error('Error updating application status:', error);
      alert('Could not update application status. Please try again.');
    }
  };

  const verifySavedJobs = async () => {
    setVerifyingJobs(true);
    setVerificationProgress(5);
    setVerificationMessage('Starting saved job verification...');
    setVerificationLogs(['Starting saved job verification...']);

    try {
      const response = await fetch('http://localhost:8000/api/jobs/verify/start', { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || 'Could not start verification.');

      const verificationId = data.verification_id;
      const poller = window.setInterval(async () => {
        try {
          const statusResponse = await fetch(`http://localhost:8000/api/search/status/${verificationId}`, { cache: 'no-store' });
          if (!statusResponse.ok) throw new Error(`Verification status failed (${statusResponse.status})`);
          const status = await statusResponse.json();
          if (status.logs) setVerificationLogs(status.logs);
          if (typeof status.progress === 'number') setVerificationProgress(status.progress);
          if (status.message) setVerificationMessage(status.message);

          if (status.status === 'complete' || status.status === 'error') {
            window.clearInterval(poller);
            setVerifyingJobs(false);
            if (status.status === 'complete') await fetchJobs(false);
          }
        } catch (pollError) {
          window.clearInterval(poller);
          setVerifyingJobs(false);
          setVerificationMessage(pollError instanceof Error ? pollError.message : 'Verification failed.');
        }
      }, 1200);
    } catch (error) {
      setVerifyingJobs(false);
      setVerificationMessage(error instanceof Error ? error.message : 'Could not start verification.');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (files.length === 0) return;

    setLoading(true);
    setSearchMessage('Starting live search...');
    setProgress(5);
    setProgressLabel('Starting job search...');
    setLiveLogs(['Starting job search...']);
    setDownloadUrl(null);

    const formData = new FormData();
    files.forEach((selectedFile) => formData.append('files', selectedFile));
    formData.append('target_roles', targetRoles);
    formData.append('excluded_roles', excludedRoles);
    formData.append('reuse_cv_analysis', String(reuseCvAnalysis));

    try {
      const startResponse = await fetch('http://localhost:8000/api/search/start', {
        method: 'POST',
        body: formData,
      });

      if (!startResponse.ok) {
        let message = 'Failed to start search';
        try {
          const errorData = await startResponse.json();
          if (errorData?.detail) message = errorData.detail;
          else if (typeof errorData?.message === 'string') message = errorData.message;
        } catch {
          try {
            const text = await startResponse.text();
            if (text) message = text;
          } catch {
            message = 'Failed to start search';
          }
        }
        throw new Error(message);
      }

      const startData = await startResponse.json();
      const activeSearchId = startData.search_id;
      setSearchId(activeSearchId);
      setSearchMessage(`Search started. Polling live logs...`);

      const pollStatus = async () => {
        try {
          const statusResponse = await fetch(`http://localhost:8000/api/search/status/${activeSearchId}`);
          if (statusResponse.status === 404) {
            setLoading(false);
            setProgress(0);
            setProgressLabel('Search session expired');
            setSearchMessage('The backend restarted and this search session was lost. Start the search again.');
            setLiveLogs((prev) => [...prev, 'Search session expired. Please start the search again.']);
            return true;
          }
          if (!statusResponse.ok) {
            throw new Error(`Status request failed (${statusResponse.status})`);
          }
          const statusData = await statusResponse.json();

          if (statusData?.logs) setLiveLogs(statusData.logs);
          if (statusData?.message?.includes('saved them to CSV')) {
            void fetchJobs(false);
          }
          if (typeof statusData.progress === 'number') setProgress(statusData.progress);
          if (statusData?.message) setProgressLabel(statusData.message);
          if (statusData?.message) setSearchMessage(statusData.message);

          if (statusData?.status === 'complete') {
            setProgress(100);
            setProgressLabel('Search complete');
            setSearchMessage('Search completed! Excel file ready.');
            setLoading(false);
            setDownloadUrl(statusData.download_url ? `http://localhost:8000${statusData.download_url}` : null);
            setTimeout(() => fetchJobs(), 500);
            return true;
          }

          if (statusData?.status === 'error') {
            setProgress(0);
            setProgressLabel('Search failed');
            setSearchMessage(statusData.error || 'The search failed.');
            setLoading(false);
            alert(statusData.error || 'The search failed.');
            return true;
          }

          return false;
        } catch (error) {
          console.error('Polling error:', error);
          return false;
        }
      };

      let finished = false;
      const poller = window.setInterval(async () => {
        if (finished) {
          window.clearInterval(poller);
          return;
        }
        const done = await pollStatus();
        if (done) {
          finished = true;
          window.clearInterval(poller);
        }
      }, 1200);

    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : 'An error occurred during the search process.';

      console.error(error);
      setProgress(0);
      setProgressLabel('Search failed');
      setSearchMessage(message);
      setLiveLogs((prev) => [...prev, message]);
      alert(message);
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (jobs.length === 0) return;

    const worksheet = XLSX.utils.json_to_sheet(jobs);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Job Matches');

    const excelBuffer = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
    const blob = new Blob([excelBuffer], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'job_matches.xlsx';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const filteredJobs = jobs
    .map((job, index) => ({ job, index }))
    .filter(({ job }) => {
      const searchableText = [job['Job Title'], job.Company, job.Location]
        .join(' ')
        .toLowerCase();
      const score = parseInt(job['Fit Score (%)']?.toString().replace('%', '') || '0', 10);
      const matchesText = !jobFilter.trim() || searchableText.includes(jobFilter.trim().toLowerCase());
      const matchesWorkingType = workingTypeFilter === 'All' || job['Working Type'] === workingTypeFilter;
      const matchesScore = minimumScore === '0' || Number.isNaN(score) || score >= Number(minimumScore);
      const hasSalary = Boolean(job.Salary && job.Salary !== 'Not specified');
      const matchesSalary = salaryFilter === 'All' ||
        (salaryFilter === 'Available' && hasSalary) ||
        (salaryFilter === 'Not specified' && !hasSalary);
      const ageDays = getPostedAgeDays(job['Posted Date']);
      const matchesPostedDate = postedDateFilter === 'All' ||
        (postedDateFilter === 'Not specified' && ageDays === null) ||
        (postedDateFilter === '24h' && ageDays !== null && ageDays <= 1) ||
        (postedDateFilter === '3d' && ageDays !== null && ageDays <= 3) ||
        (postedDateFilter === '7d' && ageDays !== null && ageDays <= 7) ||
        (postedDateFilter === 'Older' && ageDays !== null && ageDays > 7);
      return matchesText && matchesWorkingType && matchesScore && matchesSalary && matchesPostedDate;
    });

  const verificationCounts = jobs.reduce<Record<string, number>>((counts, job) => {
    const status = job['Verification Status'] || 'Not verified';
    counts[status] = (counts[status] || 0) + 1;
    return counts;
  }, {});

  return (
    <main className="min-h-screen w-full px-4 py-6 font-sans md:px-8 lg:px-10">
      <header className="mb-10 text-center">
        <h1 className="text-4xl font-bold mb-2 tracking-tight">CareerMatch</h1>
        <p className="text-gray-500">Upload your CV to discover roles that match your experience.</p>
      </header>

      <div className="bg-white p-8 rounded-2xl shadow-sm border border-gray-100 mb-10">
        <form onSubmit={handleSubmit} className="flex flex-col items-center">
          
          {/* Dropzone Area */}
          <div 
            className={`flex flex-col items-center justify-center w-full h-48 border-2 border-dashed rounded-xl transition relative
              ${dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-gray-50 hover:bg-gray-100'}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            {files.length === 0 ? (
              <label className="flex flex-col items-center justify-center w-full h-full cursor-pointer">
                <Upload className={`w-10 h-10 mb-3 ${dragActive ? 'text-blue-500' : 'text-gray-400'}`} />
                <p className="mb-2 text-sm text-gray-500"><span className="font-semibold">Click to upload CVs</span> or drag and drop</p>
                <p className="text-xs text-gray-500">Select one or more PDF/DOCX files (Max 10MB each)</p>
                <input 
                  type="file" 
                  className="hidden" 
                  accept=".pdf,.docx" 
                  multiple
                  onChange={handleFileChange} 
                  ref={fileInputRef}
                />
              </label>
            ) : (
              <div className="flex flex-col items-center justify-center w-full h-full gap-3 p-4">
                <div className="flex w-full flex-nowrap items-center justify-start gap-2 overflow-x-auto overflow-y-hidden">
                  <Briefcase className="w-10 h-10 shrink-0 text-blue-500" />
                  {files.map((selectedFile) => (
                    <div key={selectedFile.name} className="shrink-0 whitespace-nowrap text-sm text-gray-800 font-medium px-4 py-2 bg-blue-100 rounded-lg flex items-center gap-2">
                      {selectedFile.name}
                      <button type="button" onClick={() => removeFile(selectedFile.name)} className="p-1 hover:bg-blue-200 rounded-full transition text-red-500">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
                <label className="shrink-0 cursor-pointer text-sm text-blue-600 hover:underline">
                  Add more CVs
                  <input type="file" className="hidden" accept=".pdf,.docx" multiple onChange={handleFileChange} />
                </label>
              </div>
            )}
          </div>

          <div className="grid w-full gap-4 mt-6 md:grid-cols-2">
            <label className="text-sm text-gray-700">
              <span className="mb-2 block font-medium">Target roles</span>
              <textarea
                value={targetRoles}
                onChange={(e) => setTargetRoles(e.target.value)}
                placeholder="One role per line, or separate roles with commas. Leave blank for default roles."
                rows={5}
                className="w-full rounded-lg border border-gray-300 p-3 text-sm focus:border-blue-500 focus:outline-none"
              />
            </label>
            <label className="text-sm text-gray-700">
              <span className="mb-2 block font-medium">Excluded roles</span>
              <textarea
                value={excludedRoles}
                onChange={(e) => setExcludedRoles(e.target.value)}
                placeholder="Roles to exclude, one per line. Leave blank for default exclusions."
                rows={5}
                className="w-full rounded-lg border border-gray-300 p-3 text-sm focus:border-blue-500 focus:outline-none"
              />
            </label>
          </div>
          <div className="mt-3 flex w-full flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={saveRolePreferences}
              className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100"
            >
              Save role preferences
            </button>
            <button
              type="button"
              onClick={clearSavedRolePreferences}
              className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
            >
              Clear saved preferences
            </button>
          </div>
          <label className="mt-4 flex w-full items-center gap-3 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={reuseCvAnalysis}
              onChange={(event) => setReuseCvAnalysis(event.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span>
              Reuse saved CV analysis when available
              <span className="ml-1 text-gray-500">(uncheck to analyze the uploaded CVs again)</span>
            </span>
          </label>

          <button 
            type="submit" 
            disabled={files.length === 0 || loading}
            className="mt-6 px-8 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-all shadow-sm hover:shadow-md"
          >
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Briefcase className="w-5 h-5" />}
            {loading ? 'Agents Running (This takes a moment)...' : 'Run Search Pipeline'}
          </button>
        </form>
      </div>

      {/* Search Message */}
      {searchMessage && (
        <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg text-blue-800 text-sm flex items-center gap-2">
          <Briefcase className="w-4 h-4" />
          {searchMessage}
        </div>
      )}

      {loading && (
        <div className="mb-6 rounded-xl border border-blue-100 bg-white p-4 shadow-sm">
          <div className="mb-2 flex items-center justify-between text-sm text-gray-700">
            <span className="font-medium">Search progress</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-gray-200">
            <div
              className="h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="mt-3 text-sm text-gray-600">{progressLabel || 'Starting the job search pipeline...'}</p>

          <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Live logs</p>
            <div className="space-y-2 max-h-44 overflow-auto text-xs text-gray-700">
              {liveLogs.length === 0 ? (
                <p>Waiting for the first backend update...</p>
              ) : (
                liveLogs.map((log, index) => (
                  <p key={`${log}-${index}`} className="border-l border-blue-200 pl-2">{log}</p>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      <section className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Verify saved jobs</h2>
            <p className="mt-1 text-sm text-gray-700">Ask AI to check whether saved roles still exist, prioritizing official company websites.</p>
          </div>
          <button
            type="button"
            onClick={verifySavedJobs}
            disabled={verifyingJobs || jobs.length === 0}
            className="rounded-md bg-amber-700 px-4 py-2 text-sm font-medium text-white hover:bg-amber-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {verifyingJobs ? 'Verifying jobs...' : 'Verify saved jobs'}
          </button>
        </div>
        {(verifyingJobs || verificationMessage) && (
          <div className="mt-4">
            <div className="mb-2 flex justify-between text-sm text-gray-700">
              <span>{verificationMessage}</span>
              <span>{verificationProgress}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-amber-200">
              <div className="h-full rounded-full bg-amber-700 transition-all" style={{ width: `${verificationProgress}%` }} />
            </div>
            <div className="mt-3 max-h-32 overflow-auto text-xs text-gray-700">
              {verificationLogs.map((log, index) => <p key={`${log}-${index}`} className="border-l border-amber-300 pl-2">{log}</p>)}
            </div>
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-2 text-xs font-medium">
          {['Active', 'Expired', 'Blocked', 'Not found', 'Not verified'].map((status) => (
            <span key={status} className="rounded-full bg-white px-3 py-1 text-gray-700">
              {status}: {verificationCounts[status] || 0}
            </span>
          ))}
        </div>
      </section>

      {/* Results Table Section */}
      {jobs.length > 0 && (
        <section>
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-2xl font-bold">📋 Job Matches ({filteredJobs.length} of {jobs.length})</h2>
            <div className="flex gap-2">
              <button 
                onClick={() => fetchJobs()}
                className="flex items-center gap-2 text-sm bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition shadow-sm"
              >
                <RefreshCw className="w-4 h-4" /> Refresh
              </button>
              <button
                onClick={handleDownload}
                disabled={jobs.length === 0}
                className="flex items-center gap-2 text-sm bg-gray-900 text-white px-4 py-2 rounded-md hover:bg-gray-800 transition shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <FileDown className="w-4 h-4" /> Download Excel
              </button>
            </div>
          </div>

          <div className="mb-6 grid gap-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm md:grid-cols-[minmax(0,1fr)_180px_180px_180px_180px]">
            <label className="text-sm text-gray-700">
              <span className="mb-2 flex items-center gap-2 font-medium"><Filter className="h-4 w-4" /> Search jobs</span>
              <input
                type="search"
                value={jobFilter}
                onChange={(event) => setJobFilter(event.target.value)}
                placeholder="Title, company, or location"
                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-blue-500 focus:outline-none"
              />
            </label>
            <label className="text-sm text-gray-700">
              <span className="mb-2 block font-medium">Working type</span>
              <select
                value={workingTypeFilter}
                onChange={(event) => setWorkingTypeFilter(event.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-blue-500 focus:outline-none"
              >
                <option>All</option>
                <option>Remote</option>
                <option>Hybrid</option>
                <option>On-site</option>
                <option>Not specified</option>
              </select>
            </label>
            <label className="text-sm text-gray-700">
              <span className="mb-2 block font-medium">Minimum match</span>
              <select
                value={minimumScore}
                onChange={(event) => setMinimumScore(event.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-blue-500 focus:outline-none"
              >
                <option value="0">Any score</option>
                <option value="70">70%+</option>
                <option value="80">80%+</option>
                <option value="90">90%+</option>
              </select>
            </label>
            <label className="text-sm text-gray-700">
              <span className="mb-2 block font-medium">Salary</span>
              <select
                value={salaryFilter}
                onChange={(event) => setSalaryFilter(event.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-blue-500 focus:outline-none"
              >
                <option>All</option>
                <option value="Available">Salary available</option>
                <option value="Not specified">Not specified</option>
              </select>
            </label>
            <label className="text-sm text-gray-700">
              <span className="mb-2 block font-medium">Posted date</span>
              <select
                value={postedDateFilter}
                onChange={(event) => setPostedDateFilter(event.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-blue-500 focus:outline-none"
              >
                <option>All</option>
                <option value="24h">Last 24 hours</option>
                <option value="3d">Last 3 days</option>
                <option value="7d">Last 7 days</option>
                <option value="Older">Older than 7 days</option>
                <option value="Not specified">Not specified</option>
              </select>
            </label>
          </div>
          
          <div className="overflow-x-auto bg-white rounded-xl shadow-sm border border-gray-100">
            <table className="w-full text-left text-sm text-gray-600">
              <thead className="bg-gray-50 border-b border-gray-200 sticky top-0">
                <tr>
                  <th className="px-6 py-4 font-semibold text-gray-900">Job Title</th>
                  <th className="px-6 py-4 font-semibold text-gray-900">Company</th>
                  <th className="px-6 py-4 font-semibold text-gray-900">Location</th>
                  <th className="px-6 py-4 font-semibold text-gray-900">Posted Date</th>
                  <th className="px-6 py-4 font-semibold text-gray-900">Working Type</th>
                  <th className="px-6 py-4 font-semibold text-gray-900">Salary</th>
                  <th className="px-6 py-4 font-semibold text-gray-900">Verification</th>
                  <th className="px-6 py-4 font-semibold text-gray-900">Match Score</th>
                  <th className="px-6 py-4 font-semibold text-gray-900">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredJobs.map(({ job, index }) => {
                  const scoreStr = job['Fit Score (%)']?.toString().replace('%', '') || '0';
                  const score = parseInt(scoreStr);
                  
                  return (
                    <tr key={index} className="hover:bg-gray-50 transition">
                      <td className="px-6 py-4 font-medium text-gray-900">{job['Job Title']}</td>
                      <td className="px-6 py-4 text-gray-700">{job['Company']}</td>
                      <td className="px-6 py-4 flex items-center gap-1 text-gray-700">
                        <MapPin className="w-3 h-3"/> 
                        {job['Location']}
                      </td>
                      <td className="px-6 py-4 text-gray-700">{formatPostedDate(job['Posted Date'])}</td>
                      <td className="px-6 py-4 text-gray-700">{job['Working Type'] || 'Not specified'}</td>
                      <td className="px-6 py-4 text-gray-700">{job.Salary || 'Not specified'}</td>
                      <td className="px-6 py-4">
                        <span className={`rounded-full px-3 py-1 text-xs font-medium ${
                          job['Verification Status'] === 'Active' ? 'bg-green-100 text-green-700' :
                          job['Verification Status'] === 'Expired' ? 'bg-red-100 text-red-700' :
                          job['Verification Status'] === 'Blocked' ? 'bg-yellow-100 text-yellow-700' :
                          'bg-gray-100 text-gray-600'
                        }`}>
                          {job['Verification Status'] || 'Not verified'}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`px-3 py-1 rounded-full text-xs font-bold whitespace-nowrap ${
                          score >= 85 ? 'bg-green-100 text-green-700' : 
                          score >= 70 ? 'bg-yellow-100 text-yellow-700' : 
                          'bg-gray-100 text-gray-700'
                        }`}>
                          {job['Fit Score (%)']}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-6 py-4">
                        <a
                          href={`/jobs/${index}`}
                          target="_blank"
                          rel="noreferrer"
                          className="mr-2 inline-block text-blue-600 hover:text-blue-800 font-medium text-xs hover:underline"
                        >
                          More details
                        </a>
                        {getPreferredJobUrl(job) ? (
                          <a 
                            href={getPreferredJobUrl(job) || '#'} 
                            target="_blank" 
                            rel="noreferrer"
                            className="inline-block text-blue-600 hover:text-blue-800 font-medium text-xs hover:underline"
                          >
                            View →
                          </a>
                        ) : (
                          <span className="text-gray-400 text-xs">N/A</span>
                        )}
                        <button
                          type="button"
                          onClick={() => updateApplied(job, job.Applied !== 'Yes')}
                          title={job.Applied === 'Yes' ? 'Mark as not applied' : 'Mark as applied'}
                          className={`ml-2 inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ${job.Applied === 'Yes' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600 hover:bg-green-50 hover:text-green-700'}`}
                        >
                          {job.Applied === 'Yes' ? 'Applied' : 'Mark applied'}
                        </button>
                        <button
                          type="button"
                          onClick={() => dismissJob(job)}
                          title="Remove this job from your listings"
                          className="ml-2 inline-flex items-center text-gray-500 hover:text-red-600"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Empty State */}
      {jobs.length === 0 && !loading && (
        <div className="text-center py-12 text-gray-500">
          <Briefcase className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>No jobs found. Upload your CV to start searching!</p>
        </div>
      )}
    </main>
  );
}