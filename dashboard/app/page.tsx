"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Mail,
  RefreshCw,
  Send,
  Activity,
  AlertTriangle,
  CalendarClock,
  Inbox,
  Tag,
  Zap,
  Calendar,
  CheckCircle2,
  Clock,
  Settings,
  Smartphone,
  User,
  Save,
  Pause,
  Play,
  X
} from "lucide-react";

// ─── Constants ─────────────────────────────────────────────────────────
const API_BASE = "http://localhost:8000";

// ─── Types ─────────────────────────────────────────────────────────────
interface Analysis {
  category: string | null;
  summary: string | null;
  deadline: string | null;
  deadline_iso: string | null;
  action_required: string | null;
  execution_tier: string | null;
  is_important: boolean;
}

interface EmailRecord {
  id: number;
  gmail_message_id: string;
  sender: string | null;
  subject: string | null;
  status: string;
  processed_at: string | null;
  analysis: Analysis | null;
}

interface Stats {
  total_processed: number;
  important_alerts: number;
  upcoming_deadlines: number;
}

interface SchedulerSettings {
  is_paused: boolean;
  interval_minutes: int;
}

// ─── Helpers ───────────────────────────────────────────────────────────
function extractDomain(sender: string | null): string {
  if (!sender) return "";
  const match = sender.match(/@([\w.-]+)/);
  return match ? match[1] : "";
}

function categoryColor(cat: string | null): string {
  switch (cat?.toLowerCase()) {
    case "placement":
      return "bg-blue-50 text-blue-700 border border-blue-200";
    case "exam":
      return "bg-red-50 text-red-700 border border-red-200";
    case "academic":
      return "bg-emerald-50 text-emerald-700 border border-emerald-200";
    case "scholarship":
      return "bg-amber-50 text-amber-700 border border-amber-200";
    case "fee":
      return "bg-orange-50 text-orange-700 border border-orange-200";
    case "internship":
      return "bg-violet-50 text-violet-700 border border-violet-200";
    default:
      return "bg-slate-100 text-slate-600 border border-slate-200";
  }
}

function tierColor(tier: string | null): string {
  switch (tier?.toUpperCase()) {
    case "GEMINI":
      return "bg-indigo-50 text-indigo-700 border border-indigo-200";
    case "GROQ":
      return "bg-fuchsia-50 text-fuchsia-700 border border-fuchsia-200";
    default:
      return "bg-slate-100 text-slate-500 border border-slate-200";
  }
}

function formatDeadline(isoStr: string | null): string {
  if (!isoStr) return "";
  try {
    return new Date(isoStr).toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

function timeAgo(isoStr: string | null): string {
  if (!isoStr) return "";
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ─── Toast ─────────────────────────────────────────────────────────────
function Toast({
  message,
  type,
  onClose,
}: {
  message: string;
  type: "success" | "error";
  onClose: () => void;
}) {
  useEffect(() => {
    const t = setTimeout(onClose, 3500);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div
      className={`fixed top-6 right-6 z-50 flex items-center gap-2 rounded-lg px-5 py-3 text-sm font-medium shadow-lg transition-all
        ${type === "success" ? "bg-emerald-600 text-white" : "bg-red-600 text-white"}`}
    >
      {type === "success" ? (
        <CheckCircle2 size={16} />
      ) : (
        <AlertTriangle size={16} />
      )}
      {message}
    </div>
  );
}

// ─── Skeleton Loaders ──────────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="animate-skeleton h-4 w-3/4 rounded bg-slate-100 mb-3" />
      <div className="animate-skeleton h-3 w-1/2 rounded bg-slate-100 mb-2" />
      <div className="animate-skeleton h-3 w-full rounded bg-slate-100 mb-2" />
      <div className="animate-skeleton h-3 w-2/3 rounded bg-slate-100" />
    </div>
  );
}

function SkeletonStat() {
  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm">
      <div className="animate-skeleton h-3 w-1/2 rounded bg-slate-100 mb-3" />
      <div className="animate-skeleton h-8 w-1/3 rounded bg-slate-100" />
    </div>
  );
}

// ─── Main Dashboard ────────────────────────────────────────────────────
export default function Dashboard() {
  const [emails, setEmails] = useState<EmailRecord[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [digestSending, setDigestSending] = useState(false);
  
  // Scheduler State
  const [schedulerSettings, setSchedulerSettings] = useState<SchedulerSettings>({ is_paused: false, interval_minutes: 15 });
  const [updatingScheduler, setUpdatingScheduler] = useState(false);

  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
  } | null>(null);
  
  const [phone, setPhone] = useState("");
  const [phoneSaved, setPhoneSaved] = useState(false);
  const [gmail, setGmail] = useState("");
  const [gmailSaved, setGmailSaved] = useState(false);

  // Feed Filters & Pagination
  const [activeFilter, setActiveFilter] = useState<"ALL" | "IMPORTANT" | "DEADLINES">("ALL");
  const [visibleCount, setVisibleCount] = useState(3);
  const [dismissedIds, setDismissedIds] = useState<Set<number>>(new Set());

  const showToast = useCallback(
    (message: string, type: "success" | "error") => {
      setToast({ message, type });
    },
    []
  );

  // ── Fetch data ─────────────────────────────────────────────────────
  const fetchData = useCallback(async () => {
    try {
      const [emailsRes, statsRes, schedulerRes] = await Promise.all([
        fetch(`${API_BASE}/emails/history?limit=15`),
        fetch(`${API_BASE}/status`),
        fetch(`${API_BASE}/settings/scheduler`),
      ]);

      if (emailsRes.ok) {
        const emailsJson = await emailsRes.json();
        setEmails(emailsJson.data ?? []);
      }
      if (statsRes.ok) {
        const statsJson = await statsRes.json();
        setStats(statsJson.data ?? null);
      }
      if (schedulerRes.ok) {
        const schedulerJson = await schedulerRes.json();
        if (schedulerJson.data) {
           setSchedulerSettings({
             is_paused: schedulerJson.data.is_paused,
             interval_minutes: schedulerJson.data.interval_minutes
           });
        }
      }
    } catch {
      // Backend may be down — silent fail on poll
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30_000); // UI poll every 30s
    return () => clearInterval(interval);
  }, [fetchData]);

  // ── Actions ────────────────────────────────────────────────────────
  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await fetch(`${API_BASE}/trigger/sync`, { method: "POST" });
      if (res.ok) {
        showToast("Sync triggered — checking inbox now!", "success");
        setTimeout(fetchData, 3000);
      } else {
        showToast("Sync request failed.", "error");
      }
    } catch {
      showToast("Cannot reach backend server.", "error");
    } finally {
      setSyncing(false);
    }
  };

  const handleDigest = async () => {
    setDigestSending(true);
    try {
      const res = await fetch(`${API_BASE}/trigger/digest`, {
        method: "POST",
      });
      if (res.ok) {
        showToast("Daily digest sent to WhatsApp!", "success");
      } else {
        showToast("Digest request failed.", "error");
      }
    } catch {
      showToast("Cannot reach backend server.", "error");
    } finally {
      setDigestSending(false);
    }
  };

  const updateScheduler = async (updates: Partial<SchedulerSettings>) => {
    setUpdatingScheduler(true);
    const newSettings = { ...schedulerSettings, ...updates };
    // Optimistic update
    setSchedulerSettings(newSettings);
    
    try {
      const res = await fetch(`${API_BASE}/settings/scheduler`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newSettings)
      });
      if (res.ok) {
        showToast("Monitoring settings updated.", "success");
        const json = await res.json();
        if(json.data) {
            setSchedulerSettings(json.data);
        }
      } else {
        showToast("Failed to update monitoring settings.", "error");
        fetchData(); // Revert
      }
    } catch {
      showToast("Cannot reach backend server.", "error");
      fetchData(); // Revert
    } finally {
      setUpdatingScheduler(false);
    }
  };

  const togglePause = () => {
    updateScheduler({ is_paused: !schedulerSettings.is_paused });
  };

  const handleCadenceChange = (minutes: number) => {
    updateScheduler({ interval_minutes: minutes });
  };

  const handleSavePhone = () => {
    setPhoneSaved(true);
    showToast("Phone number saved (local only).", "success");
    setTimeout(() => setPhoneSaved(false), 2000);
  };

  const handleSaveGmail = () => {
    setGmailSaved(true);
    showToast("Gmail address saved (local only).", "success");
    setTimeout(() => setGmailSaved(false), 2000);
  };

  const handleDismiss = (id: number) => {
    setDismissedIds((prev) => new Set(prev).add(id));
  };

  // Filter and limit emails
  const filteredEmails = emails.filter((email) => {
    if (dismissedIds.has(email.id)) return false;
    if (activeFilter === "IMPORTANT" && !email.analysis?.is_important) return false;
    if (activeFilter === "DEADLINES" && !email.analysis?.deadline_iso) return false;
    return true;
  });

  const visibleEmails = filteredEmails.slice(0, visibleCount);

  return (
    <div className="min-h-screen bg-slate-50 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-blue-50 via-slate-50 to-emerald-50/30">
      {/* Toast */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}

      {/* ────────────────────── HEADER ────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600 text-white shadow-sm">
              <Mail size={20} />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-slate-900 leading-tight">
                Inbox Notifier
              </h1>
              <p className="text-xs text-slate-400">
                Email → AI → WhatsApp Pipeline
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Interactive Health Pill */}
            <button 
              onClick={togglePause}
              disabled={updatingScheduler}
              className={`hidden sm:flex items-center gap-2 rounded-full border px-3.5 py-1.5 transition-colors ${
                schedulerSettings.is_paused 
                  ? "border-amber-200 bg-amber-50 hover:bg-amber-100" 
                  : "border-emerald-200 bg-emerald-50 hover:bg-emerald-100"
              }`}
            >
              {!schedulerSettings.is_paused ? (
                <>
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
                  </span>
                  <span className="text-xs font-medium text-emerald-700">Active</span>
                </>
              ) : (
                <>
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-500" />
                  </span>
                  <span className="text-xs font-medium text-amber-700">Paused</span>
                </>
              )}
            </button>

            <button
              id="sync-btn"
              onClick={handleSync}
              disabled={syncing}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-60"
            >
              <RefreshCw size={15} className={syncing ? "animate-spin" : ""} />
              {syncing ? "Syncing…" : "Sync Now"}
            </button>

            <button
              id="digest-btn"
              onClick={handleDigest}
              disabled={digestSending}
              className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:opacity-60"
            >
              <Send size={15} />
              <span className="hidden sm:inline">{digestSending ? "Sending…" : "Send Digest"}</span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8 space-y-8">
        {/* ────────────── AUTOMATION CONFIG CARD ────────────── */}
        <section
          id="settings-card"
          className="rounded-xl border border-slate-200/80 bg-white/70 backdrop-blur-md shadow-sm overflow-hidden"
        >
          <div className="border-b border-slate-100 bg-gradient-to-r from-slate-50 to-blue-50/30 px-6 py-4 flex items-center justify-between">
             <div className="flex items-center gap-2">
                <Settings size={18} className="text-slate-500" />
                <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
                  Connected Identity & Sync
                </h2>
             </div>
             
             {/* Dynamic Polling Selector */}
             <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-slate-500 mr-1">Sync Cadence:</span>
                <select
                   value={schedulerSettings.interval_minutes}
                   onChange={(e) => handleCadenceChange(Number(e.target.value))}
                   disabled={updatingScheduler}
                   className="text-xs bg-white border border-slate-200 rounded-md py-1 px-2 text-slate-700 outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-400 disabled:opacity-60 cursor-pointer"
                >
                   <option value={15}>Every 15 mins</option>
                   <option value={30}>Every 30 mins</option>
                   <option value={60}>Every 1 hour</option>
                   <option value={120}>Every 2 hours</option>
                   <option value={360}>Every 6 hours</option>
                </select>
             </div>
          </div>
          
          <div className="grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-100">
            {/* Linked Gmail */}
            <div className="flex items-start gap-4 p-6 transition hover:bg-slate-50/30">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-100 text-blue-600">
                <User size={18} />
              </div>
              <div className="flex-1">
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
                  Linked Gmail Account
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <input
                    id="gmail-input"
                    type="email"
                    placeholder="student@university.ac.in"
                    value={gmail}
                    onChange={(e) => setGmail(e.target.value)}
                    className="w-full max-w-[200px] rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-800 outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                  />
                  <button
                    id="save-gmail-btn"
                    onClick={handleSaveGmail}
                    className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-blue-700"
                  >
                    <Save size={13} />
                    {gmailSaved ? "Saved" : "Save"}
                  </button>
                </div>
              </div>
            </div>

            {/* WhatsApp Number */}
            <div className="flex items-start gap-4 p-6 transition hover:bg-slate-50/30">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                <Smartphone size={18} />
              </div>
              <div className="flex-1">
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
                  WhatsApp Recipient Target
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <input
                    id="phone-input"
                    type="tel"
                    placeholder="+91 98765 43210"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="w-full max-w-[200px] rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-800 outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                  />
                  <button
                    id="save-phone-btn"
                    onClick={handleSavePhone}
                    className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-blue-700"
                  >
                    <Save size={13} />
                    {phoneSaved ? "Saved" : "Save"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ────────────── METRIC STAT CARDS ────────────── */}
        <section id="stats-grid" className="grid gap-5 sm:grid-cols-3">
          {loading ? (
            <>
              <SkeletonStat />
              <SkeletonStat />
              <SkeletonStat />
            </>
          ) : (
            <>
              <div className="group relative overflow-hidden rounded-xl border border-blue-100 bg-gradient-to-br from-white to-blue-50/50 p-6 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg hover:border-blue-300 cursor-pointer">
                <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-400 to-blue-500"></div>
                <div className="flex items-center justify-between mb-4">
                  <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                    Total Processed
                  </p>
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 text-blue-600 transition-transform duration-300 group-hover:scale-110 shadow-sm">
                    <Inbox size={20} />
                  </div>
                </div>
                <p className="text-3xl font-extrabold text-slate-900 tracking-tight">
                  {stats?.total_processed ?? 0}
                </p>
                <p className="mt-1 text-xs font-medium text-slate-500">emails analyzed</p>
              </div>

              <div className="group relative overflow-hidden rounded-xl border border-amber-100 bg-gradient-to-br from-white to-amber-50/50 p-6 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg hover:border-amber-300 cursor-pointer">
                <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-amber-400 to-amber-500"></div>
                <div className="flex items-center justify-between mb-4">
                  <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                    Important Alerts
                  </p>
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-600 transition-transform duration-300 group-hover:scale-110 shadow-sm">
                    <AlertTriangle size={20} />
                  </div>
                </div>
                <p className="text-3xl font-extrabold text-slate-900 tracking-tight">
                  {stats?.important_alerts ?? 0}
                </p>
                <p className="mt-1 text-xs font-medium text-slate-500">
                  flagged as critical
                </p>
              </div>

              <div className="group relative overflow-hidden rounded-xl border border-rose-100 bg-gradient-to-br from-white to-rose-50/50 p-6 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg hover:border-rose-300 cursor-pointer">
                <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-rose-400 to-rose-500"></div>
                <div className="flex items-center justify-between mb-4">
                  <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                    Upcoming Deadlines
                  </p>
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-100 text-rose-600 transition-transform duration-300 group-hover:scale-110 shadow-sm">
                    <CalendarClock size={20} />
                  </div>
                </div>
                <p className="text-3xl font-extrabold text-slate-900 tracking-tight">
                  {stats?.upcoming_deadlines ?? 0}
                </p>
                <p className="mt-1 text-xs font-medium text-slate-500">
                  deadlines tracked
                </p>
              </div>
            </>
          )}
        </section>

        {/* ────────────── EMAIL FEED ────────────── */}
        <section id="email-feed">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div className="flex items-center gap-2">
              <Activity size={20} className="text-slate-700" />
              <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wide">
                Recent Analysis Feed
              </h2>
            </div>
            
            <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
               <button onClick={() => setActiveFilter("ALL")} className={`px-3 py-1.5 text-xs font-bold rounded-full transition-colors ${activeFilter === "ALL" ? "bg-slate-800 text-white" : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"}`}>All</button>
               <button onClick={() => setActiveFilter("IMPORTANT")} className={`px-3 py-1.5 text-xs font-bold rounded-full transition-colors ${activeFilter === "IMPORTANT" ? "bg-amber-500 text-white" : "bg-white text-amber-700 hover:bg-amber-50 border border-amber-200"}`}>Important</button>
               <button onClick={() => setActiveFilter("DEADLINES")} className={`px-3 py-1.5 text-xs font-bold rounded-full transition-colors ${activeFilter === "DEADLINES" ? "bg-rose-500 text-white" : "bg-white text-rose-700 hover:bg-rose-50 border border-rose-200"}`}>Deadlines</button>
               
               <div className="hidden sm:block w-px h-5 bg-slate-300 mx-2"></div>
               
               <div className="flex items-center gap-1.5 text-xs font-medium text-slate-400 shrink-0">
                 <Clock size={12} />
                 Auto-refreshing (30s)
               </div>
            </div>
          </div>

          {loading ? (
            <div className="grid gap-4">
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : emails.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white py-20 text-center shadow-sm">
              <div className="h-16 w-16 bg-blue-50 text-blue-500 rounded-full flex items-center justify-center mb-4">
                 <Inbox size={32} />
              </div>
              <h3 className="text-lg font-semibold text-slate-800 mb-1">Your Inbox is Clear</h3>
              <p className="text-sm text-slate-500 max-w-sm mb-6">
                We haven't processed any emails yet. Wait for the background worker to sync, or trigger one manually.
              </p>
              <button
                onClick={handleSync}
                disabled={syncing}
                className="flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-md transition hover:bg-blue-700 hover:shadow-lg disabled:opacity-60"
              >
                 <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
                 Force Sync Now
              </button>
            </div>
          ) : (
            <div className="grid gap-4">
              {visibleEmails.map((email) => (
                <article
                  key={email.id}
                  id={`email-card-${email.id}`}
                  className="group relative overflow-hidden rounded-xl border border-slate-200/80 bg-white/80 backdrop-blur-sm p-5 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg hover:border-blue-300/80 cursor-pointer"
                >
                  {/* Decorative left border for important emails */}
                  {email.analysis?.is_important && (
                     <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-gradient-to-b from-amber-400 to-orange-500 shadow-[0_0_8px_rgba(251,191,36,0.6)]"></div>
                  )}
                  
                  {/* Header */}
                  <div className="flex flex-wrap items-start justify-between gap-3 mb-3 pl-1">
                    <div className="flex-1 min-w-0">
                      <h3 className="text-base font-bold text-slate-900 leading-snug truncate">
                        {email.subject || "No Subject"}
                      </h3>
                      <p className="text-xs font-medium text-slate-500 mt-1">
                        <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded-md mr-2">{extractDomain(email.sender) || "unknown"}</span>
                        {email.processed_at && (
                          <span className="text-slate-400">
                            {timeAgo(email.processed_at)}
                          </span>
                        )}
                      </p>
                    </div>

                    {/* Badges and Actions */}
                    <div className="flex items-center gap-1.5 shrink-0">
                      {email.analysis?.category && (
                        <span
                          className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-bold tracking-wide uppercase ${categoryColor(email.analysis.category)}`}
                        >
                          <Tag size={10} />
                          {email.analysis.category}
                        </span>
                      )}
                      {email.analysis?.execution_tier && (
                        <span
                          className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-bold tracking-wide uppercase ${tierColor(email.analysis.execution_tier)}`}
                        >
                          <Zap size={10} />
                          {email.analysis.execution_tier}
                        </span>
                      )}
                      <button
                        onClick={() => handleDismiss(email.id)}
                        className="ml-1 p-1 rounded bg-slate-100 hover:bg-rose-100 text-slate-400 hover:text-rose-600 transition-colors"
                        title="Dismiss"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  </div>

                  {/* Summary */}
                  {email.analysis?.summary && (
                    <p className="text-sm text-slate-600 leading-relaxed mb-4 pl-1">
                      {email.analysis.summary}
                    </p>
                  )}

                  {/* Footer: deadline + action */}
                  <div className="flex flex-wrap items-center gap-3 pl-1 mt-auto pt-3 border-t border-slate-50">
                    {email.analysis?.deadline_iso && (
                      <span className="inline-flex items-center gap-1.5 rounded-md bg-rose-50 border border-rose-200 px-3 py-1 text-[12px] font-bold text-rose-700">
                        <Calendar size={12} />
                        Due: {formatDeadline(email.analysis.deadline_iso)}
                      </span>
                    )}
                    {!email.analysis?.deadline_iso &&
                      email.analysis?.deadline &&
                      email.analysis.deadline !== "Not Specified" && (
                        <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-50 border border-slate-200 px-3 py-1 text-[12px] font-semibold text-slate-600">
                          <Calendar size={12} />
                          {email.analysis.deadline}
                        </span>
                      )}
                    {email.analysis?.action_required && (
                      <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-slate-500">
                        <CheckCircle2
                          size={12}
                          className="text-emerald-500"
                        />
                        <span className="truncate max-w-[300px]">
                          {email.analysis.action_required}
                        </span>
                      </span>
                    )}
                  </div>
                </article>
              ))}
              
              {filteredEmails.length > visibleCount && (
                 <div className="mt-4 text-center">
                   <button
                     onClick={() => setVisibleCount((prev) => prev + 3)}
                     className="px-6 py-2.5 text-sm font-semibold text-blue-600 bg-white border border-slate-200 rounded-full hover:bg-slate-50 hover:border-slate-300 hover:shadow-sm transition-all"
                   >
                     Load More Emails
                   </button>
                 </div>
              )}
            </div>
          )}
        </section>
      </main>

      {/* ────────────── FOOTER ────────────── */}
      <footer className="border-t border-slate-200/80 bg-white mt-12">
        <div className="mx-auto max-w-7xl px-6 py-6 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-400 gap-4">
          <span className="font-medium">
            Inbox Notifier v1.0 — Automated Email Intelligence
          </span>
          <span className="flex items-center gap-1.5 font-medium bg-slate-50 px-3 py-1.5 rounded-full border border-slate-100">
            <Zap size={12} className="text-emerald-500" />
            Powered by Gemini + WhatsApp Cloud API
          </span>
        </div>
      </footer>
    </div>
  );
}
