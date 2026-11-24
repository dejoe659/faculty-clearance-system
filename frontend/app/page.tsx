"use client";

import {
  ArrowDownToLine, ArrowRight, Bell, BookOpenCheck, Check, CheckCircle2, ChevronDown,
  CircleHelp, ClipboardCheck, FileCheck2, FileText, GraduationCap, LayoutDashboard,
  ListChecks, LogOut, Menu, Plus, Printer, Search, Settings2, ShieldCheck, Upload,
  Users, X
} from "lucide-react";
import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
type Role = "student" | "departmental_officer" | "faculty_officer" | "faculty_admin" | "super_admin";
type User = {
  id: string; role: Role; full_name: string; matric_no: string | null; email: string; phone: string;
  faculty: string; department: string; programme: string; level: string; admission_year: string; graduation_year: string;
};
type Requirement = {
  id: string; title: string; description: string; category: string; department: string;
  assigned_role: string; mandatory: number | boolean; position: number; active: number | boolean;
};
type Submission = Requirement & {
  application_id: string; status: string; filename: string | null; original_filename: string | null;
  comment: string; submitted_at: string | null; full_name: string; matric_no: string; student_id: string;
  level: string; session: string;
};
type Application = {
  id: string; student_id: string; full_name: string; matric_no: string; department: string; faculty: string; level: string;
  session: string; status: string; verification_code: string; total: number; approved: number;
  pending: number; needs_action: number; progress: number; created_at: string;
};
type Dashboard = {
  role: Role; application?: Application | null; counts: Record<string, number>;
  notifications?: { id: string; message: string; created_at: string; read: number }[];
  applications?: Application[]; submissions?: Submission[];
};
type Section = "Overview" | "Clearance" | "Review queue" | "Requirements" | "Students" | "Reports" | "Activity" | "Profile" | "Certificate";
type RequirementDraft = Omit<Requirement, "id">;

const sectionsFor = (role: Role): { name: Section; icon: typeof LayoutDashboard }[] => {
  if (role === "student") return [
    { name: "Overview", icon: LayoutDashboard }, { name: "Clearance", icon: ListChecks }, { name: "Profile", icon: Users }
  ];
  const sections: { name: Section; icon: typeof LayoutDashboard }[] = [
    { name: "Overview", icon: LayoutDashboard }, { name: "Review queue", icon: ClipboardCheck }, { name: "Students", icon: Users }
  ];
  if (role === "faculty_admin" || role === "super_admin") sections.push(
    { name: "Requirements", icon: Settings2 }, { name: "Reports", icon: FileCheck2 }
  );
  if (role === "super_admin") sections.push({ name: "Activity", icon: ShieldCheck });
  sections.push({ name: "Profile", icon: Users });
  return sections;
};

const blankRequirement: RequirementDraft = {
  title: "", description: "", category: "Department", department: "",
  assigned_role: "departmental_officer", mandatory: true, position: 0, active: true
};

async function api(path: string, token: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API}${path}`, { ...options, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { message = (await response.json()).detail || message; } catch { /* use the HTTP status */ }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function initials(name: string) {
  return name.split(/\s+/).slice(0, 2).map(part => part[0] || "").join("").toUpperCase();
}
function roleName(role: Role) {
  return ({ student: "Student", departmental_officer: "Department officer", faculty_officer: "Faculty officer", faculty_admin: "Faculty administrator", super_admin: "Super administrator" })[role];
}
function statusName(status: string) {
  return ({ approved: "Approved", submitted: "Under review", rejected: "Rejected", changes_requested: "Correction needed", outstanding: "Outstanding", in_progress: "In progress", fully_cleared: "Fully cleared" })[status] || status.replaceAll("_", " ");
}
function dateLabel(value: string) {
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(false);
  const [active, setActive] = useState<Section>("Overview");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [students, setStudents] = useState<User[]>([]);
  const [report, setReport] = useState<{ departments: { department: string; applications: number; fully_cleared: number }[] } | null>(null);
  const [activity, setActivity] = useState<{ id: string; actor_name: string; action: string; target_id: string; created_at: string }[]>([]);
  const [certificate, setCertificate] = useState<Application & { programme: string } | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [registerMode, setRegisterMode] = useState(false);
  const [review, setReview] = useState<Submission | null>(null);
  const [reviewComment, setReviewComment] = useState("");
  const [requirementDraft, setRequirementDraft] = useState<RequirementDraft>(blankRequirement);
  const [editingRequirement, setEditingRequirement] = useState<string | null>(null);
  const [mobileNav, setMobileNav] = useState(false);

  const notify = useCallback((message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(""), 4500);
  }, []);

  const loadWorkspace = useCallback(async (auth: string, currentUser: User) => {
    const [stats, required, appRows] = await Promise.all([
      api("/api/dashboard", auth), api("/api/requirements", auth), api("/api/applications", auth)
    ]) as [Dashboard, Requirement[], Application[]];
    setDashboard(stats);
    setRequirements(required);
    setApplications(appRows);
    if (currentUser.role === "student") {
      if (stats.application) {
        const own = await api(`/api/applications/${stats.application.id}/submissions`, auth) as Submission[];
        setSubmissions(own);
      } else setSubmissions([]);
    } else {
      const visibleApps = currentUser.role === "departmental_officer"
        ? appRows.filter(application => application.department === currentUser.department)
        : appRows;
      const perApplication = await Promise.all(visibleApps.map(application =>
        api(`/api/applications/${application.id}/submissions`, auth) as Promise<Submission[]>
      ));
      setSubmissions(perApplication.flat());
    }
    if (currentUser.role === "faculty_admin" || currentUser.role === "super_admin") {
      setStudents(await api("/api/admin/users", auth));
      setReport(await api("/api/admin/report", auth));
    }
    if (currentUser.role === "super_admin") setActivity(await api("/api/admin/activity", auth));
  }, []);

  useEffect(() => {
    const savedToken = window.sessionStorage.getItem("clearance-token") || "";
    if (!savedToken) { setReady(true); return; }
    setToken(savedToken);
    api("/api/auth/me", savedToken)
      .then(async (currentUser: User) => {
        setUser(currentUser);
        await loadWorkspace(savedToken, currentUser);
      })
      .catch(() => { window.sessionStorage.removeItem("clearance-token"); setToken(""); })
      .finally(() => setReady(true));
  }, [loadWorkspace]);

  const filteredSubmissions = useMemo(() => submissions.filter(item => {
    const matchesText = `${item.full_name} ${item.matric_no} ${item.title} ${item.category}`.toLowerCase().includes(search.toLowerCase());
    return matchesText && (statusFilter === "all" || item.status === statusFilter);
  }), [submissions, search, statusFilter]);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    try {
      const result = await api("/api/auth/login", "", {
        method: "POST", body: JSON.stringify({ identifier: form.get("identifier"), password: form.get("password") })
      }) as { token: string; user: User };
      setToken(result.token); setUser(result.user);
      window.sessionStorage.setItem("clearance-token", result.token);
      await loadWorkspace(result.token, result.user);
      setActive("Overview");
    } catch (error) {
      window.sessionStorage.removeItem("clearance-token");
      setToken(""); setUser(null);
      notify(error instanceof Error ? error.message : "Unable to sign in.");
    } finally { setBusy(false); setReady(true); }
  }

  async function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries());
    setBusy(true);
    try {
      await api("/api/auth/register", "", { method: "POST", body: JSON.stringify(payload) });
      notify("Account created. Sign in with your matriculation number and password.");
      setRegisterMode(false);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to create account.");
    } finally { setBusy(false); }
  }

  async function refresh() {
    if (!user || !token) return;
    try { await loadWorkspace(token, user); }
    catch (error) { notify(error instanceof Error ? error.message : "Could not refresh data."); }
  }

  async function logout() {
    try { await api("/api/auth/logout", token, { method: "POST" }); } catch { /* clear local session either way */ }
    window.sessionStorage.removeItem("clearance-token");
    setToken(""); setUser(null); setDashboard(null); setSubmissions([]); setApplications([]);
  }

  async function startApplication() {
    setBusy(true);
    try {
      await api("/api/applications", token, { method: "POST" });
      await refresh();
      setActive("Clearance");
      notify("Your clearance application is ready.");
    } catch (error) { notify(error instanceof Error ? error.message : "Could not start the application."); }
    finally { setBusy(false); }
  }

  async function uploadDocument(event: ChangeEvent<HTMLInputElement>, submission: Submission) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) { notify("The maximum document size is 10 MB."); return; }
    const data = new FormData(); data.append("file", file);
    setBusy(true);
    try {
      await api(`/api/submissions/${submission.id}/upload`, token, { method: "POST", body: data });
      await refresh(); notify("Document submitted for review.");
    } catch (error) { notify(error instanceof Error ? error.message : "Could not upload the document."); }
    finally { setBusy(false); event.target.value = ""; }
  }

  async function downloadDocument(submission: Submission) {
    try {
      const response = await fetch(`${API}/api/submissions/${submission.id}/file`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error("Document could not be opened.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = submission.original_filename || "clearance-document";
      link.click(); URL.revokeObjectURL(url);
    } catch (error) { notify(error instanceof Error ? error.message : "Document could not be opened."); }
  }

  async function previewDocument(submission: Submission) {
    const previewWindow = window.open("about:blank", "_blank");
    if (!previewWindow) { notify("Allow pop-ups to preview this document."); return; }
    try {
      const response = await fetch(`${API}/api/submissions/${submission.id}/file?preview=true`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error("Document could not be previewed.");
      const url = URL.createObjectURL(await response.blob());
      previewWindow.location.href = url;
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      previewWindow.close();
      notify(error instanceof Error ? error.message : "Document could not be previewed.");
    }
  }

  async function saveReview(decision: "approved" | "rejected" | "changes_requested") {
    if (!review) return;
    if (decision === "approved" && !window.confirm(`Approve ${review.title} for ${review.full_name}?`)) return;
    if (decision === "rejected" && !window.confirm(`Reject ${review.title} for ${review.full_name}?`)) return;
    if (decision !== "approved" && !reviewComment.trim()) { notify("Add a reason or correction request."); return; }
    setBusy(true);
    try {
      await api(`/api/submissions/${review.id}/review`, token, {
        method: "PATCH", body: JSON.stringify({ decision, comment: reviewComment })
      });
      setReview(null); setReviewComment(""); await refresh();
      notify(decision === "approved" ? "Clearance requirement approved." : "Review decision sent to the student.");
    } catch (error) { notify(error instanceof Error ? error.message : "Could not save this decision."); }
    finally { setBusy(false); }
  }

  async function saveRequirement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    try {
      const path = editingRequirement ? `/api/requirements/${editingRequirement}` : "/api/requirements";
      await api(path, token, { method: editingRequirement ? "PATCH" : "POST", body: JSON.stringify(requirementDraft) });
      setRequirementDraft(blankRequirement); setEditingRequirement(null); await refresh();
      notify(editingRequirement ? "Requirement updated." : "Requirement added.");
    } catch (error) { notify(error instanceof Error ? error.message : "Could not save requirement."); }
    finally { setBusy(false); }
  }

  async function createStaff(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusy(true);
    try {
      await api("/api/admin/users", token, { method: "POST", body: JSON.stringify(Object.fromEntries(form.entries())) });
      formElement.reset();
      await refresh();
      notify("Staff account created and assigned.");
    } catch (error) { notify(error instanceof Error ? error.message : "Could not create staff account."); }
    finally { setBusy(false); }
  }

  function editRequirement(item: Requirement) {
    setEditingRequirement(item.id);
    setRequirementDraft({
      title: item.title, description: item.description, category: item.category, department: item.department,
      assigned_role: item.assigned_role, mandatory: Boolean(item.mandatory), position: item.position, active: Boolean(item.active)
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function removeRequirement(item: Requirement) {
    if (!window.confirm(`Remove "${item.title}" from future applications?`)) return;
    try { await api(`/api/requirements/${item.id}`, token, { method: "DELETE" }); await refresh(); notify("Requirement removed."); }
    catch (error) { notify(error instanceof Error ? error.message : "Could not remove requirement."); }
  }

  async function showCertificate(applicationId: string) {
    try {
      setCertificate(await api(`/api/applications/${applicationId}/certificate`, token));
      setActive("Certificate");
    } catch (error) { notify(error instanceof Error ? error.message : "Certificate is not available yet."); }
  }

  if (!ready) return <main className="loading-screen"><div className="brand-mark"><GraduationCap size={24} /></div><span>Loading your clearance workspace…</span></main>;
  if (!user) return <AuthScreen registerMode={registerMode} setRegisterMode={setRegisterMode} onSignIn={signIn} onRegister={register} busy={busy} />;

  const nav = sectionsFor(user.role);
  const studentApp = dashboard?.application;
  const heading = active === "Overview" ? (user.role === "student" ? "Your clearance" : roleName(user.role) + " dashboard") : active;

  return (
    <main className="app-shell">
      <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
        <a className="brand" href="#" onClick={event => { event.preventDefault(); setActive("Overview"); }}>
          <span className="brand-mark"><GraduationCap size={21} /></span><span>Clearance<span className="brand-accent">Hub</span></span>
        </a>
        <div className="workspace-switch"><span className="workspace-avatar">N</span><span className="workspace-copy"><strong>Northstar University</strong><small>{user.faculty}</small></span><ChevronDown size={15} /></div>
        <span className="nav-caption">WORKSPACE</span>
        <nav className="nav-list" aria-label="Main navigation">
          {nav.map(({ name, icon: Icon }) => <button key={name} className={`nav-item ${active === name ? "active" : ""}`} onClick={() => { setActive(name); setMobileNav(false); }}>
            <Icon size={18} strokeWidth={1.8} /><span>{name}</span>
            {name === "Review queue" && (dashboard?.counts.pending || 0) > 0 && <span className="nav-count">{dashboard?.counts.pending}</span>}
          </button>)}
        </nav>
        <div className="sidebar-spacer" />
        <div className="side-help"><div className="help-icon"><CircleHelp size={17} /></div><div><strong>Need help?</strong><small>Contact the clearance office</small></div><ArrowRight size={15} /></div>
        <div className="profile-card"><div className="profile-avatar">{initials(user.full_name)}</div><div className="profile-copy"><strong>{user.full_name}</strong><small>{roleName(user.role)}</small></div><button className="icon-button profile-menu" title="Sign out" onClick={logout}><LogOut size={17} /></button></div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open menu" onClick={() => setMobileNav(!mobileNav)}><Menu size={19} /></button>
          <div className="breadcrumb"><span>Workspace</span><span className="crumb-slash">/</span><strong>{heading}</strong></div>
          <div className="top-actions"><span className="session-pill"><span />2025 / 2026 session</span>
            <button className="icon-button notification-button" aria-label="Notifications" onClick={() => setActive("Overview")}><Bell size={18} />{dashboard?.notifications?.some(item => !item.read) && <i />}</button>
            <div className="top-avatar">{initials(user.full_name)}</div>
          </div>
        </header>
        <div className="content">
          {active === "Overview" && <Overview user={user} dashboard={dashboard} submissions={submissions} onNavigate={setActive} onStart={startApplication} onCertificate={showCertificate} busy={busy} />}
          {active === "Clearance" && <ClearancePage application={studentApp || null} submissions={submissions} onStart={startApplication} onUpload={uploadDocument} onDownload={downloadDocument} onPreview={previewDocument} onCertificate={showCertificate} busy={busy} />}
          {active === "Review queue" && <ReviewQueue items={filteredSubmissions} search={search} setSearch={setSearch} filter={statusFilter} setFilter={setStatusFilter} onReview={item => { setReview(item); setReviewComment(item.comment || ""); }} onDownload={downloadDocument} onPreview={previewDocument} />}
          {active === "Requirements" && <RequirementsPage items={requirements} draft={requirementDraft} setDraft={setRequirementDraft} editing={editingRequirement} onSubmit={saveRequirement} onEdit={editRequirement} onDelete={removeRequirement} onCancel={() => { setEditingRequirement(null); setRequirementDraft(blankRequirement); }} busy={busy} />}
          {active === "Students" && <StudentsPage students={students} applications={applications} submissions={submissions} isAdmin={user.role === "faculty_admin" || user.role === "super_admin"} canCreateAdmins={user.role === "super_admin"} onCreateStaff={createStaff} busy={busy} />}
          {active === "Reports" && <ReportsPage report={report} dashboard={dashboard} />}
          {active === "Activity" && <ActivityPage items={activity} />}
          {active === "Profile" && <ProfilePage user={user} />}
          {active === "Certificate" && certificate && <CertificatePage certificate={certificate} />}
        </div>
      </section>
      {mobileNav && <button className="nav-scrim" aria-label="Close navigation" onClick={() => setMobileNav(false)} />}
      {notice && <div className="toast" role="status"><CheckCircle2 size={18} />{notice}<button onClick={() => setNotice("")} aria-label="Dismiss"><X size={15} /></button></div>}
      {review && <ReviewModal item={review} comment={reviewComment} setComment={setReviewComment} busy={busy} onClose={() => setReview(null)} onDecision={saveReview} onDownload={() => downloadDocument(review)} onPreview={() => previewDocument(review)} />}
    </main>
  );
}

function AuthScreen({ registerMode, setRegisterMode, onSignIn, onRegister, busy }: {
  registerMode: boolean; setRegisterMode: (value: boolean) => void; onSignIn: (event: FormEvent<HTMLFormElement>) => void;
  onRegister: (event: FormEvent<HTMLFormElement>) => void; busy: boolean;
}) {
  return <main className="auth-page">
    <section className="auth-art"><div className="auth-brand"><span className="brand-mark"><GraduationCap size={22} /></span>Clearance<span>Hub</span></div>
      <div className="auth-message"><span className="auth-kicker">NORTHSTAR UNIVERSITY</span><h1>Your next chapter<br />starts <em>cleared.</em></h1><p>Complete every clearance step online. No queues, no office-to-office visits, just a clear path to graduation.</p>
        <div className="auth-feature"><span><Check size={15} /></span>One connected clearance journey</div><div className="auth-feature"><span><Check size={15} /></span>Real-time updates from your faculty</div></div>
      <div className="auth-art-footer">A simpler way to cross the finish line.</div>
    </section>
    <section className="auth-panel"><div className="auth-form-wrap">
      <div className="auth-mobile-brand"><span className="brand-mark"><GraduationCap size={22} /></span>ClearanceHub</div>
      <span className="eyebrow">{registerMode ? "STUDENT REGISTRATION" : "SECURE UNIVERSITY PORTAL"}</span>
      <h2>{registerMode ? "Create your account" : "Welcome back"}</h2><p className="auth-subtitle">{registerMode ? "Use your university details to get started." : "Sign in to continue your clearance journey."}</p>
      {registerMode ? <form onSubmit={onRegister}>
        <div className="form-grid">
          <Field label="Full name"><input required name="full_name" placeholder="e.g. Amina Yusuf" /></Field>
          <Field label="Matriculation number"><input required name="matric_no" placeholder="e.g. CSC/22/0418" /></Field>
          <Field label="University email"><input required type="email" name="email" placeholder="you@northstar.edu" /></Field>
          <Field label="Phone number"><input name="phone" placeholder="+234 800 000 0000" /></Field>
          <Field label="Faculty"><input required name="faculty" defaultValue="Faculty of Science" /></Field>
          <Field label="Department"><input required name="department" defaultValue="Computer Science" /></Field>
          <Field label="Programme"><input required name="programme" defaultValue="B.Sc. Computer Science" /></Field>
          <Field label="Current level"><select name="level" defaultValue="400"><option>100</option><option>200</option><option>300</option><option>400</option><option>500</option></select></Field>
          <Field label="Admission year"><input required name="admission_year" defaultValue="2022" /></Field>
          <Field label="Expected graduation"><input required name="graduation_year" defaultValue="2026" /></Field>
          <Field label="Password"><input required type="password" name="password" minLength={10} placeholder="At least 10 characters" /></Field>
        </div>
        <button className="button button-primary auth-submit" disabled={busy}>{busy ? "Creating account…" : "Create student account"}<ArrowRight size={16} /></button>
      </form> : <form onSubmit={onSignIn}>
        <Field label="Matriculation number or staff email"><input required name="identifier" autoComplete="username" placeholder="e.g. CSC/22/0418" /></Field>
        <Field label="Password"><input required type="password" name="password" autoComplete="current-password" placeholder="Enter your password" /></Field>
        <button className="button button-primary auth-submit" disabled={busy}>{busy ? "Signing in…" : "Sign in securely"}<ArrowRight size={16} /></button>
        <div className="demo-box"><ShieldCheck size={16} /><span><strong>Demo access</strong><small>Matric: CSC/22/0418 · Staff: evelyn.officer@northstar.edu<br />Password for all demo accounts: Clearance123!</small></span></div>
      </form>}
      <div className="auth-switch">{registerMode ? "Already registered?" : "New student?"}<button onClick={() => setRegisterMode(!registerMode)}>{registerMode ? "Sign in" : "Create an account"}</button></div>
      <div className="auth-privacy"><ShieldCheck size={14} />Your academic records are protected and only shared with assigned officers.</div>
    </div></section>
  </main>;
}

function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) {
  return <div className="page-header"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>;
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}
function StatCard({ label, value, detail, icon: Icon, tone }: { label: string; value: number | string; detail: string; icon: typeof Users; tone: string }) {
  return <article className="stat-card"><div className={`stat-icon ${tone}`}><Icon size={19} /></div><div className="stat-copy"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div><div className="stat-decoration" /></article>;
}
function StatusBadge({ status }: { status: string }) {
  return <span className={`status-pill status-${status}`}>{status === "approved" && <Check size={12} />}{statusName(status)}</span>;
}
function ProgressBar({ value }: { value: number }) {
  return <div className="progress-track" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${value}%` }} /></div>;
}

function Overview({ user, dashboard, submissions, onNavigate, onStart, onCertificate, busy }: {
  user: User; dashboard: Dashboard | null; submissions: Submission[]; onNavigate: (section: Section) => void;
  onStart: () => void; onCertificate: (id: string) => void; busy: boolean;
}) {
  if (user.role === "student") {
    const application = dashboard?.application;
    const counts = dashboard?.counts || {};
    const progress = application?.progress || 0;
    return <>
      <PageHeader eyebrow={`${user.faculty.toUpperCase()} · ${user.department.toUpperCase()}`} title={`Welcome, ${user.full_name.split(" ")[0]}`} description="Here's your personal clearance overview for the 2025 / 2026 session." action={application ? <button className="button button-primary" onClick={() => onNavigate("Clearance")}><ListChecks size={16} />Continue clearance</button> : undefined} />
      <div className="student-hero"><div className="hero-copy"><span className="hero-label"><span />CLEARANCE APPLICATION</span><h2>{application ? (progress === 100 ? "You’re all cleared!" : "You’re making progress.") : "Your clearance journey starts here."}</h2><p>{application ? "Complete the remaining requirements and track each review from your dashboard." : "Start one online application to submit and track all faculty clearance requirements."}</p>
        {application ? <div className="hero-progress"><ProgressBar value={progress} /><div><strong>{progress}%</strong><span>{application.approved} of {application.total} requirements approved</span></div></div>
          : <button className="button button-primary" onClick={onStart} disabled={busy}><Plus size={16} />{busy ? "Preparing…" : "Start clearance application"}<ArrowRight size={15} /></button>}
      </div><div className="hero-illustration"><div className="hero-ring ring-one" /><div className="hero-ring ring-two" /><div className="hero-doc"><FileCheck2 size={40} /><span><Check size={12} /></span></div><div className="hero-dot dot-one" /><div className="hero-dot dot-two" /></div></div>
      <div className="stats-grid">
        <StatCard label="Approved" value={counts.approved || 0} detail="Requirements complete" icon={CheckCircle2} tone="green" />
        <StatCard label="Under review" value={counts.submitted || 0} detail="With your clearance officers" icon={ClipboardCheck} tone="blue" />
        <StatCard label="Corrections" value={(counts.rejected || 0) + (counts.changes_requested || 0)} detail="Need your attention" icon={FileText} tone="rose" />
        <StatCard label="Outstanding" value={counts.outstanding || 0} detail="Waiting for your submission" icon={ListChecks} tone="amber" />
      </div>
      <div className="dashboard-grid">
        <section className="card">
          <div className="card-heading"><div><h2>Clearance checklist</h2><p>{application ? "Your latest requirement status." : "Start an application to see your checklist."}</p></div><button className="text-button" onClick={() => onNavigate("Clearance")}>View all <ArrowRight size={14} /></button></div>
          {submissions.length ? <div className="requirement-list">{submissions.slice(0, 5).map(item => <RequirementRow key={item.id} item={item} />)}</div>
            : <EmptyState title="No application yet" description="Your checklist will appear here after you start clearance." />}
        </section>
        <section className="card notification-card">
          <div className="card-heading"><div><h2>Recent updates</h2><p>Messages about your clearance.</p></div><Bell size={17} className="muted-icon" /></div>
          {(dashboard?.notifications || []).length ? <div className="notification-list">{dashboard?.notifications?.slice(0, 4).map(item => <div className="notification-row" key={item.id}><span className="notification-dot" /><div><p>{item.message}</p><small>{dateLabel(item.created_at)}</small></div></div>)}</div>
            : <EmptyState title="You're up to date" description="New review decisions will appear here." />}
          {application?.status === "fully_cleared" && <button className="certificate-link" onClick={() => onCertificate(application.id)}><ShieldCheck size={16} />View clearance certificate<ArrowRight size={14} /></button>}
        </section>
      </div>
      <div className="profile-strip"><div className="profile-strip-icon"><GraduationCap size={19} /></div><div><strong>{user.programme}</strong><span>{user.matric_no} · Level {user.level} · Class of {user.graduation_year}</span></div><button className="text-button" onClick={() => onNavigate("Profile")}>View profile <ArrowRight size={14} /></button></div>
    </>;
  }

  const counts = dashboard?.counts || {};
  const admin = user.role === "faculty_admin" || user.role === "super_admin";
  return <>
    <PageHeader eyebrow="CLEARANCE OPERATIONS" title={`Good day, ${user.full_name.split(" ")[0]}`} description={admin ? "Monitor student clearance and manage the faculty workflow." : `Review your ${user.department || "faculty"} clearance submissions.`} />
    <div className="stats-grid">
      {admin ? <>
        <StatCard label="Registered students" value={counts.students || 0} detail="In this faculty workspace" icon={Users} tone="blue" />
        <StatCard label="Clearance applications" value={counts.applications || 0} detail="Submitted by students" icon={FileText} tone="violet" />
        <StatCard label="Fully cleared" value={counts.fully_cleared || 0} detail="All requirements approved" icon={CheckCircle2} tone="green" />
        <StatCard label="Staff accounts" value={counts.staff || 0} detail="Officers and administrators" icon={ShieldCheck} tone="amber" />
      </> : <>
        <StatCard label="Assigned students" value={dashboard?.applications?.length || 0} detail="Students in your queue" icon={Users} tone="blue" />
        <StatCard label="Pending submissions" value={counts.pending || 0} detail="Require your review" icon={ClipboardCheck} tone="amber" />
        <StatCard label="Approved" value={counts.approved || 0} detail="Requirements cleared" icon={CheckCircle2} tone="green" />
        <StatCard label="Needs correction" value={counts.rejected || 0} detail="Returned to students" icon={FileText} tone="rose" />
      </>}
    </div>
    <div className="dashboard-grid staff-grid">
      <section className="card">
        <div className="card-heading"><div><h2>Recent submissions</h2><p>Latest documents from students in your queue.</p></div><button className="text-button" onClick={() => onNavigate("Review queue")}>Review queue <ArrowRight size={14} /></button></div>
        <div className="table-scroll"><table className="data-table"><thead><tr><th>STUDENT</th><th>REQUIREMENT</th><th>SUBMITTED</th><th>STATUS</th></tr></thead><tbody>
          {(dashboard?.submissions || []).slice(0, 5).map(item => <tr key={item.id}><td><strong>{item.full_name}</strong><small>{item.matric_no}</small></td><td>{item.title}</td><td>{item.submitted_at ? dateLabel(item.submitted_at) : "—"}</td><td><StatusBadge status={item.status} /></td></tr>)}
          {!dashboard?.submissions?.length && <tr><td colSpan={4} className="table-blank">No submissions waiting for review.</td></tr>}
        </tbody></table></div>
      </section>
      <section className="card quick-card"><div className="card-heading"><div><h2>Quick access</h2><p>Keep your workflow moving.</p></div></div>
        <button className="quick-link" onClick={() => onNavigate("Review queue")}><span className="quick-icon quick-blue"><ClipboardCheck size={17} /></span><span><strong>Open review queue</strong><small>Review documents and send decisions</small></span><ArrowRight size={15} /></button>
        {admin && <button className="quick-link" onClick={() => onNavigate("Requirements")}><span className="quick-icon quick-purple"><Settings2 size={17} /></span><span><strong>Manage requirements</strong><small>Configure the clearance checklist</small></span><ArrowRight size={15} /></button>}
        {admin && <button className="quick-link" onClick={() => onNavigate("Reports")}><span className="quick-icon quick-green"><FileCheck2 size={17} /></span><span><strong>View faculty report</strong><small>Review clearance completion</small></span><ArrowRight size={15} /></button>}
      </section>
    </div>
  </>;
}

function RequirementRow({ item }: { item: Submission }) {
  return <div className="requirement-row"><span className={`requirement-icon icon-${item.status}`}><FileCheck2 size={16} /></span><div className="requirement-copy"><strong>{item.title}</strong><small>{item.category}{item.mandatory ? " · Mandatory" : " · Optional"}</small></div><StatusBadge status={item.status} /></div>;
}
function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="empty-state"><div><FileText size={18} /></div><strong>{title}</strong><span>{description}</span></div>;
}

function ClearancePage({ application, submissions, onStart, onUpload, onDownload, onPreview, onCertificate, busy }: {
  application: Application | null; submissions: Submission[]; onStart: () => void;
  onUpload: (event: ChangeEvent<HTMLInputElement>, item: Submission) => void; onDownload: (item: Submission) => void;
  onPreview: (item: Submission) => void;
  onCertificate: (id: string) => void; busy: boolean;
}) {
  return <>
    <PageHeader eyebrow="STUDENT WORKSPACE" title="Clearance checklist" description="Submit documents and follow each requirement through review." action={application && application.status === "fully_cleared" ? <button className="button button-secondary" onClick={() => onCertificate(application.id)}><ShieldCheck size={16} />View certificate</button> : undefined} />
    {!application ? <section className="card start-card"><span className="start-icon"><BookOpenCheck size={23} /></span><h2>Start your clearance application</h2><p>Your application will include each active requirement configured for your faculty and department.</p><button className="button button-primary" onClick={onStart} disabled={busy}><Plus size={16} />{busy ? "Preparing…" : "Start application"}</button></section>
      : <>
        <section className="application-summary card"><div className="application-symbol"><ClipboardCheck size={22} /></div><div className="application-copy"><span>APPLICATION · {application.session} SESSION</span><strong>{application.full_name}</strong><small>{application.matric_no} · {application.department} · Level {application.level}</small></div><div className="application-progress"><strong>{application.progress}%</strong><small>{application.approved}/{application.total} approved</small><ProgressBar value={application.progress} /></div></section>
        <section className="card checklist-card"><div className="card-heading"><div><h2>Your requirements</h2><p>Upload a PDF or image for each requirement. Max 10 MB per document.</p></div><span className="requirement-count">{submissions.length} items</span></div>
          <div className="checklist">{submissions.map(item => <article className="checklist-item" key={item.id}>
            <div className={`requirement-icon icon-${item.status}`}><FileCheck2 size={17} /></div><div className="checklist-copy"><div className="checklist-title"><strong>{item.title}</strong><StatusBadge status={item.status} /></div><p>{item.description || `Assigned to ${item.department || item.category} office.`}</p><div className="checklist-meta"><span>{item.category}</span><span>{item.mandatory ? "Mandatory" : "Optional"}</span>{item.original_filename && <><button className="inline-file" onClick={() => onPreview(item)}><FileText size={13} />Preview</button><button className="inline-file" onClick={() => onDownload(item)}><ArrowDownToLine size={12} />Download</button></>}</div>{item.comment && <div className={`review-comment ${item.status === "approved" ? "comment-approved" : ""}`}>{item.status === "approved" ? "Officer note: " : "Officer feedback: "}{item.comment}</div>}</div>
            {item.status !== "approved" && <label className={`button ${item.status === "submitted" ? "button-secondary" : "button-upload"}`}><Upload size={15} />{item.filename ? "Replace document" : item.status === "submitted" ? "Update document" : "Upload document"}<input type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" disabled={busy} onChange={event => onUpload(event, item)} /></label>}
          </article>)}</div>
        </section>
      </>}
  </>;
}

function ReviewQueue({ items, search, setSearch, filter, setFilter, onReview, onDownload, onPreview }: {
  items: Submission[]; search: string; setSearch: (value: string) => void; filter: string; setFilter: (value: string) => void;
  onReview: (item: Submission) => void; onDownload: (item: Submission) => void; onPreview: (item: Submission) => void;
}) {
  const count = items.filter(item => item.status === "submitted").length;
  return <>
    <PageHeader eyebrow="OFFICER WORKSPACE" title="Review queue" description="Review student documents and record clear, traceable decisions." />
    <div className="review-callout"><span><ShieldCheck size={19} /></span><div><strong>Every decision is recorded</strong><small>Approve a valid submission, reject it with a reason, or request a correction.</small></div><span className="queue-badge">{count} to review</span></div>
    <div className="card table-card"><div className="table-toolbar"><label className="search-box"><Search size={16} /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search name, matric no. or requirement" /></label><select className="filter-select" value={filter} onChange={event => setFilter(event.target.value)} aria-label="Filter submissions"><option value="all">All statuses</option><option value="submitted">Under review</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="changes_requested">Correction needed</option><option value="outstanding">Outstanding</option></select></div>
      <div className="table-scroll"><table className="data-table review-table"><thead><tr><th>STUDENT</th><th>CLEARANCE REQUIREMENT</th><th>DEPARTMENT / CATEGORY</th><th>SUBMITTED</th><th>STATUS</th><th>DOCUMENT</th><th /></tr></thead><tbody>
        {items.map(item => <tr key={item.id}><td><strong>{item.full_name}</strong><small>{item.matric_no} · Level {item.level}</small></td><td>{item.title}<small>{item.session} session</small></td><td>{item.department || item.category}</td><td>{item.submitted_at ? dateLabel(item.submitted_at) : "—"}</td><td><StatusBadge status={item.status} /></td><td>{item.filename ? <span className="doc-actions"><button className="row-action" onClick={() => onPreview(item)}>Preview</button><button className="row-action" onClick={() => onDownload(item)}><ArrowDownToLine size={13} />Save</button></span> : "—"}</td><td>{item.status === "submitted" || item.status === "changes_requested" || item.status === "rejected" ? <button className="row-action" onClick={() => onReview(item)}>Review <ArrowRight size={14} /></button> : <span className="muted-label">—</span>}</td></tr>)}
        {!items.length && <tr><td colSpan={7} className="table-blank">No matching clearance submissions.</td></tr>}
      </tbody></table></div>
    </div>
  </>;
}

function RequirementsPage({ items, draft, setDraft, editing, onSubmit, onEdit, onDelete, onCancel, busy }: {
  items: Requirement[]; draft: RequirementDraft; setDraft: (value: RequirementDraft) => void; editing: string | null;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void; onEdit: (item: Requirement) => void;
  onDelete: (item: Requirement) => void; onCancel: () => void; busy: boolean;
}) {
  return <>
    <PageHeader eyebrow="FACULTY CONFIGURATION" title="Clearance requirements" description="Create and organise the checklist students receive when starting an application." />
    <div className="admin-layout">
      <form className="card requirement-form" onSubmit={onSubmit}><div className="card-heading"><div><h2>{editing ? "Edit requirement" : "Add a requirement"}</h2><p>Configure the responsible office and checklist order.</p></div></div>
        <Field label="Requirement name"><input required minLength={2} value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} placeholder="e.g. Departmental clearance" /></Field>
        <Field label="Description"><textarea value={draft.description} onChange={event => setDraft({ ...draft, description: event.target.value })} rows={3} placeholder="What should the student complete?" /></Field>
        <div className="form-grid"><Field label="Category"><input required value={draft.category} onChange={event => setDraft({ ...draft, category: event.target.value })} placeholder="e.g. Department" /></Field><Field label="Department (optional)"><input value={draft.department} onChange={event => setDraft({ ...draft, department: event.target.value })} placeholder="e.g. Computer Science" /></Field>
          <Field label="Assigned officer"><select value={draft.assigned_role} onChange={event => setDraft({ ...draft, assigned_role: event.target.value })}><option value="departmental_officer">Departmental officer</option><option value="faculty_officer">Faculty officer</option></select></Field><Field label="Display order"><input type="number" min="0" value={draft.position} onChange={event => setDraft({ ...draft, position: Number(event.target.value) })} /></Field></div>
        <label className="toggle-row"><input type="checkbox" checked={Boolean(draft.mandatory)} onChange={event => setDraft({ ...draft, mandatory: event.target.checked })} /><span><strong>Mandatory requirement</strong><small>Students must complete this before being cleared.</small></span></label>
        <div className="form-actions"><button className="button button-primary" disabled={busy}><Plus size={15} />{editing ? "Save changes" : "Add requirement"}</button>{editing && <button type="button" className="button button-secondary" onClick={onCancel}>Cancel</button>}</div>
      </form>
      <section className="card requirements-admin"><div className="card-heading"><div><h2>Active checklist</h2><p>{items.length} requirements · applied to new applications</p></div></div><div className="requirement-list">{items.map((item, index) => <div className="requirement-row admin-req-row" key={item.id}><span className="order-number">{String(index + 1).padStart(2, "0")}</span><div className="requirement-copy"><strong>{item.title}</strong><small>{item.category}{item.department ? ` · ${item.department}` : ""}{item.mandatory ? " · Mandatory" : " · Optional"}</small></div><div className="req-actions"><button className="icon-button" title="Edit requirement" onClick={() => onEdit(item)}><Settings2 size={15} /></button><button className="icon-button danger-icon" title="Remove requirement" onClick={() => onDelete(item)}><X size={16} /></button></div></div>)}
        {!items.length && <EmptyState title="No requirements configured" description="Add a requirement to build your faculty checklist." />}</div></section>
    </div>
  </>;
}

function StudentsPage({ students, applications, submissions, isAdmin, canCreateAdmins, onCreateStaff, busy }: {
  students: User[]; applications: Application[]; submissions: Submission[]; isAdmin: boolean; canCreateAdmins: boolean;
  onCreateStaff: (event: FormEvent<HTMLFormElement>) => void; busy: boolean;
}) {
  const studentRows = students.filter(person => person.role === "student");
  const staffRows = students.filter(person => person.role !== "student");
  return <>
    <PageHeader eyebrow="FACULTY DIRECTORY" title="Student applications" description="Monitor registered students and their clearance progress." />
    <div className="stats-grid"><StatCard label="Registered students" value={studentRows.length} detail="Student accounts" icon={Users} tone="blue" /><StatCard label="Applications" value={applications.length} detail="Clearance applications" icon={FileText} tone="violet" /><StatCard label="Fully cleared" value={applications.filter(item => item.status === "fully_cleared").length} detail="All requirements approved" icon={CheckCircle2} tone="green" /><StatCard label="Open requirements" value={submissions.filter(item => item.status !== "approved").length} detail="Across current applications" icon={ClipboardCheck} tone="amber" /></div>
    <div className="card table-card"><div className="card-heading"><div><h2>Student directory</h2><p>Student profile and current clearance progress.</p></div></div><div className="table-scroll"><table className="data-table"><thead><tr><th>STUDENT</th><th>PROGRAMME</th><th>DEPARTMENT</th><th>LEVEL</th><th>PROGRESS</th><th>STATUS</th></tr></thead><tbody>
      {studentRows.map(person => { const application = applications.find(row => row.student_id === person.id); return <tr key={person.id}><td><strong>{person.full_name}</strong><small>{person.matric_no} · {person.email}</small></td><td>{person.programme}</td><td>{person.department}</td><td>{person.level}</td><td><div className="table-progress"><ProgressBar value={application?.progress || 0} /><small>{application?.progress || 0}%</small></div></td><td><StatusBadge status={application?.status || "outstanding"} /></td></tr>; })}
      {!studentRows.length && <tr><td colSpan={6} className="table-blank">No student accounts yet.</td></tr>}
    </tbody></table></div></div>
    {isAdmin && <div className="admin-layout staff-management">
      <form className="card requirement-form" onSubmit={onCreateStaff}><div className="card-heading"><div><h2>Add a staff member</h2><p>Create an officer account and assign its review scope.</p></div></div>
        <Field label="Full name"><input required name="full_name" minLength={2} placeholder="Staff member name" /></Field>
        <Field label="University email"><input required name="email" type="email" placeholder="name@northstar.edu" /></Field>
        <div className="form-grid"><Field label="Role"><select name="role" defaultValue="departmental_officer"><option value="departmental_officer">Departmental officer</option><option value="faculty_officer">Faculty officer</option>{canCreateAdmins && <option value="faculty_admin">Faculty administrator</option>}{canCreateAdmins && <option value="super_admin">Super administrator</option>}</select></Field>
          <Field label="Department"><input name="department" placeholder="e.g. Computer Science" /></Field></div>
        <Field label="Faculty"><input name="faculty" defaultValue="Faculty of Science" /></Field>
        <Field label="Temporary password"><input required type="password" name="password" minLength={10} placeholder="At least 10 characters" /></Field>
        <button className="button button-primary" disabled={busy}><Plus size={15} />{busy ? "Creating…" : "Create staff account"}</button>
      </form>
      <section className="card requirements-admin"><div className="card-heading"><div><h2>Staff directory</h2><p>{staffRows.length} staff accounts with workspace access.</p></div></div>
        {staffRows.length ? <div className="requirement-list">{staffRows.map(person => <div className="requirement-row" key={person.id}><div className="profile-detail-avatar staff-avatar-small">{initials(person.full_name)}</div><div className="requirement-copy"><strong>{person.full_name}</strong><small>{roleName(person.role)} · {person.department}</small></div><span className="staff-email">{person.email}</span></div>)}</div> : <EmptyState title="No staff accounts listed" description="Create an officer account to assign clearance reviews." />}
      </section>
    </div>}
  </>;
}

function ReportsPage({ report, dashboard }: { report: { departments: { department: string; applications: number; fully_cleared: number }[] } | null; dashboard: Dashboard | null }) {
  const counts = dashboard?.counts || {};
  return <>
    <PageHeader eyebrow="CLEARANCE INSIGHTS" title="Faculty reports" description="A snapshot of application volume and clearance completion by department." action={<button className="button button-secondary" onClick={() => window.print()}><Printer size={15} />Print report</button>} />
    <div className="stats-grid"><StatCard label="Applications" value={counts.applications || 0} detail="All active records" icon={FileText} tone="blue" /><StatCard label="Fully cleared" value={counts.fully_cleared || 0} detail="Ready for confirmation" icon={CheckCircle2} tone="green" /><StatCard label="In progress" value={(counts.applications || 0) - (counts.fully_cleared || 0)} detail="Not yet fully cleared" icon={ClipboardCheck} tone="amber" /></div>
    <section className="card table-card"><div className="card-heading"><div><h2>Department summary</h2><p>Student clearance applications by department.</p></div></div><div className="table-scroll"><table className="data-table"><thead><tr><th>DEPARTMENT</th><th>APPLICATIONS</th><th>FULLY CLEARED</th><th>COMPLETION</th></tr></thead><tbody>{report?.departments.map(item => <tr key={item.department}><td><strong>{item.department}</strong></td><td>{item.applications}</td><td>{item.fully_cleared}</td><td><div className="table-progress"><ProgressBar value={item.applications ? Math.round(item.fully_cleared / item.applications * 100) : 0} /><small>{item.applications ? Math.round(item.fully_cleared / item.applications * 100) : 0}%</small></div></td></tr>)}
      {!report?.departments.length && <tr><td colSpan={4} className="table-blank">No department data available.</td></tr>}</tbody></table></div></section>
  </>;
}

function ActivityPage({ items }: { items: { id: string; actor_name: string; action: string; target_id: string; created_at: string }[] }) {
  return <>
    <PageHeader eyebrow="SYSTEM OVERSIGHT" title="Activity log" description="Recent clearance review actions recorded across the system." />
    <section className="card table-card"><div className="table-scroll"><table className="data-table"><thead><tr><th>ACTOR</th><th>ACTION</th><th>RECORD</th><th>DATE</th></tr></thead><tbody>{items.map(item => <tr key={item.id}><td>{item.actor_name || "System"}</td><td><StatusBadge status={item.action} /></td><td>{item.target_id}</td><td>{dateLabel(item.created_at)}</td></tr>)}{!items.length && <tr><td colSpan={4} className="table-blank">No activity has been recorded yet.</td></tr>}</tbody></table></div></section>
  </>;
}

function ProfilePage({ user }: { user: User }) {
  return <>
    <PageHeader eyebrow="ACCOUNT INFORMATION" title="Your profile" description="Personal and academic information linked to this account." />
    <section className="card profile-detail"><div className="profile-detail-head"><div className="profile-detail-avatar">{initials(user.full_name)}</div><div><h2>{user.full_name}</h2><span>{roleName(user.role)}</span></div></div>
      <div className="profile-fields">{[
        ["Matriculation number", user.matric_no || "Staff account"], ["Email address", user.email], ["Phone number", user.phone || "Not provided"],
        ["Faculty", user.faculty], ["Department", user.department], ["Programme", user.programme],
        ["Current level", user.level], ["Admission year", user.admission_year], ["Expected graduation", user.graduation_year]
      ].map(([label, value]) => <div className="profile-field" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
    </section>
  </>;
}

function CertificatePage({ certificate }: { certificate: Application & { programme: string } }) {
  return <div className="certificate-wrap"><div className="certificate-actions"><div><span className="eyebrow">VERIFIABLE CONFIRMATION</span><h1>Clearance certificate</h1></div><button className="button button-primary" onClick={() => window.print()}><Printer size={16} />Print or save PDF</button></div>
    <article className="certificate-print"><div className="certificate-top"><span className="certificate-crest"><GraduationCap size={32} /></span><span className="certificate-university">NORTHSTAR UNIVERSITY<small>OFFICE OF THE REGISTRAR</small></span><span className="certificate-seal"><ShieldCheck size={30} /></span></div>
      <div className="certificate-rule" /><span className="certificate-kicker">FACULTY CLEARANCE CONFIRMATION</span><h2>Certificate of Clearance</h2><p className="certificate-intro">This is to certify that</p><h3>{certificate.full_name}</h3>
      <p className="certificate-body">Matriculation number <strong>{certificate.matric_no}</strong>, of the <strong>{certificate.department}</strong> Department, <strong>{certificate.faculty}</strong>, has completed all mandatory clearance requirements for the <strong>{certificate.session}</strong> academic session.</p>
      <div className="certificate-stamp"><CheckCircle2 size={17} />FULLY CLEARED</div>
      <div className="certificate-meta"><div><span>PROGRAMME</span><strong>{certificate.programme}</strong></div><div><span>LEVEL</span><strong>{certificate.level}</strong></div><div><span>VERIFICATION NUMBER</span><strong>{certificate.verification_code}</strong></div><div><span>ISSUED</span><strong>{dateLabel(new Date().toISOString())}</strong></div></div>
      <div className="certificate-footer"><span>Verify this certificate using the verification number above.</span><span className="signature-line">Registrar, Northstar University</span></div>
    </article>
  </div>;
}
function ReviewModal({ item, comment, setComment, busy, onClose, onDecision, onDownload, onPreview }: {
  item: Submission; comment: string; setComment: (value: string) => void; busy: boolean; onClose: () => void;
  onDecision: (decision: "approved" | "rejected" | "changes_requested") => void; onDownload: () => void; onPreview: () => void;
}) {
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="review-modal" role="dialog" aria-modal="true" aria-labelledby="review-title"><div className="modal-head"><div><span className="eyebrow">CLEARANCE REVIEW</span><h2 id="review-title">{item.title}</h2><p>{item.full_name} · {item.matric_no} · {item.department}</p></div><button className="icon-button" onClick={onClose} aria-label="Close review"><X size={19} /></button></div>
      <div className="modal-body"><div className="review-student"><div className="student-avatar">{initials(item.full_name)}</div><div><strong>{item.full_name}</strong><span>{item.session} session · Level {item.level}</span></div><StatusBadge status={item.status} /></div>
        <div className="document-preview"><div className="document-icon"><FileText size={23} /></div><div><strong>{item.original_filename || "No document attached"}</strong><small>{item.submitted_at ? `Submitted ${dateLabel(item.submitted_at)}` : "Student has not submitted a document"}</small></div>{item.filename && <><button className="button button-secondary" onClick={onPreview}>Preview</button><button className="button button-secondary" onClick={onDownload}><ArrowDownToLine size={15} />Download</button></>}</div>
        {item.description && <div className="requirement-description"><strong>Requirement details</strong><p>{item.description}</p></div>}
        <Field label="Decision note"><textarea rows={4} value={comment} onChange={event => setComment(event.target.value)} placeholder="Add feedback for the student. A reason is required for rejection or correction." /></Field>
        <div className="modal-actions"><button className="button button-danger" disabled={busy} onClick={() => onDecision("rejected")}>Reject</button><button className="button button-secondary" disabled={busy} onClick={() => onDecision("changes_requested")}>Request correction</button><button className="button button-primary" disabled={busy || !item.filename} onClick={() => onDecision("approved")}><Check size={16} />Approve</button></div>
      </div>
    </section>
  </div>;
}
