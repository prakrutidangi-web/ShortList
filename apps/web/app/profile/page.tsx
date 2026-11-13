"use client";

import { useCallback, useEffect, useState } from "react";
import { api, API_URL, ApiError, ProfileIn, ProfileOut, ROLE_LABELS, Suggestion } from "@/lib/api";

const TARGETABLE = ["software_engineering", "data_engineering", "ml_ai", "data_analytics"];

const EMPTY: ProfileIn = {
  skills: [],
  target_roles: ["software_engineering", "data_engineering", "ml_ai"],
  target_locations: [],
  remote_ok: true,
  grad_date: null,
  needs_sponsorship: false,
  about_text: null,
};

export default function ProfilePage() {
  const [profile, setProfile] = useState<ProfileIn>(EMPTY);
  const [saved, setSaved] = useState<ProfileOut | null>(null);
  const [pasted, setPasted] = useState("");
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [skillInput, setSkillInput] = useState("");
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const loadExisting = useCallback(async () => {
    try {
      const p = await api<ProfileOut>("/profile");
      setSaved(p);
      setProfile({
        skills: p.skills,
        target_roles: p.target_roles,
        target_locations: p.target_locations,
        remote_ok: p.remote_ok,
        grad_date: p.grad_date,
        needs_sponsorship: p.needs_sponsorship,
        about_text: p.about_text,
      });
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) setMessage({ kind: "error", text: "Cannot reach the API." });
    }
  }, []);

  useEffect(() => {
    void loadExisting();
  }, [loadExisting]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setMessage(null);
    try {
      await fn();
    } catch (e) {
      setMessage({ kind: "error", text: e instanceof ApiError ? e.message : "Cannot reach the API." });
    } finally {
      setBusy(false);
    }
  };

  const applySuggestion = (s: Suggestion) => {
    setSuggestion(s);
    setProfile((p) => ({
      ...p,
      skills: Array.from(new Set([...p.skills, ...s.skills])),
      grad_date: s.grad_date ?? p.grad_date,
    }));
  };

  const uploadPdf = (file: File) =>
    run(async () => {
      const fd = new FormData();
      fd.append("file", file);
      applySuggestion(await api<Suggestion>("/profile/resume", { method: "POST", body: fd }));
    });

  const parsePasted = () =>
    run(async () => {
      const fd = new FormData();
      fd.append("text", pasted);
      applySuggestion(await api<Suggestion>("/profile/resume", { method: "POST", body: fd }));
      setPasted(""); // do not keep the resume text around in the page once parsed
    });

  const json = (body: unknown): RequestInit => ({
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const doPreview = () =>
    run(async () => {
      const r = await api<{ profile_document: string }>("/profile/preview-document", { ...json(profile), method: "POST" });
      setPreview(r.profile_document);
    });

  const save = () =>
    run(async () => {
      const p = await api<ProfileOut>("/profile", json(profile));
      setSaved(p);
      setPreview(p.profile_document);
      setMessage({ kind: "ok", text: "Profile saved. Open the Feed to see your ranked postings." });
    });

  const remove = () => {
    if (!window.confirm("Delete your profile and everything derived from your resume, including its embedding?")) return;
    void run(async () => {
      await api("/profile", { method: "DELETE" });
      setSaved(null);
      setProfile(EMPTY);
      setSuggestion(null);
      setPreview(null);
      setMessage({ kind: "ok", text: "Deleted. Nothing about your resume remains on the server." });
    });
  };

  const addSkill = () => {
    const s = skillInput.trim();
    if (s && !profile.skills.some((x) => x.toLowerCase() === s.toLowerCase())) setProfile({ ...profile, skills: [...profile.skills, s] });
    setSkillInput("");
  };

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <div>
        <h1 className="text-xl font-semibold">Your profile</h1>
        <p className="mt-1 text-sm text-subtle">
          Your resume is read in memory to suggest skills and is <b>never stored</b>. Only the fields you confirm below, and an embedding of the text
          shown in “What gets embedded”, are saved. Names, emails and phone numbers are never extracted. Nothing is sent to any outside service.
          Backend: <code>{API_URL}</code>
        </p>
      </div>

      {message && (
        <p className={`rounded border p-3 text-sm ${message.kind === "ok" ? "border-good/40 bg-good-bg text-good" : "border-bad/40 bg-bad-bg text-bad"}`}>
          {message.text}
        </p>
      )}

      <section className="space-y-3 rounded-xl border bg-surface p-5 shadow-sm">
        <h2 className="font-medium">1. Start from your resume (optional)</h2>
        <div>
          <label className="mb-1 block text-sm" htmlFor="pdf">
            Text-based PDF (up to 5 MB; scanned PDFs are not supported)
          </label>
          <input id="pdf" type="file" accept="application/pdf" disabled={busy} onChange={(e) => e.target.files?.[0] && void uploadPdf(e.target.files[0])} />
        </div>
        <div>
          <label className="mb-1 block text-sm" htmlFor="paste">
            …or paste your resume text
          </label>
          <textarea id="paste" rows={5} className="w-full rounded border p-2 text-sm" value={pasted} onChange={(e) => setPasted(e.target.value)} />
          <button type="button" disabled={busy || pasted.trim().length < 30} onClick={() => void parsePasted()} className="mt-1 rounded bg-accent px-3 py-1.5 text-sm text-accent-ink disabled:opacity-40">
            Suggest skills from this text
          </button>
        </div>
        {suggestion && (
          <p className="text-sm text-subtle">
            Read {suggestion.characters_read} characters from your {suggestion.source}. Found {suggestion.skills.length} skills
            {suggestion.grad_date && <> and a graduation date ({suggestion.grad_date_evidence})</>}. {suggestion.note}
          </p>
        )}
      </section>

      <section className="space-y-4 rounded-xl border bg-surface p-5 shadow-sm">
        <h2 className="font-medium">2. Review and edit</h2>
        <div>
          <p className="mb-1 text-sm font-medium">Skills</p>
          <div className="flex flex-wrap gap-1.5">
            {profile.skills.map((s) => (
              <button key={s} type="button" title="Remove" onClick={() => setProfile({ ...profile, skills: profile.skills.filter((x) => x !== s) })} className="rounded bg-muted px-2 py-0.5 text-xs hover:bg-bad-bg">
                {s} ×
              </button>
            ))}
          </div>
          <div className="mt-2 flex gap-2">
            <input className="flex-1 rounded border px-2 py-1 text-sm" placeholder="Add a skill" value={skillInput} onChange={(e) => setSkillInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addSkill())} />
            <button type="button" onClick={addSkill} className="rounded border px-3 py-1 text-sm">
              Add
            </button>
          </div>
        </div>

        <fieldset>
          <legend className="mb-1 text-sm font-medium">Target roles</legend>
          <div className="flex flex-wrap gap-4 text-sm">
            {TARGETABLE.map((r) => (
              <label key={r} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={profile.target_roles.includes(r)}
                  onChange={() => setProfile({ ...profile, target_roles: profile.target_roles.includes(r) ? profile.target_roles.filter((x) => x !== r) : [...profile.target_roles, r] })}
                />
                {ROLE_LABELS[r]}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="locs">
              Target locations (comma-separated)
            </label>
            <input id="locs" className="w-full rounded border px-2 py-1 text-sm" placeholder="Seattle, New York, Canada" value={profile.target_locations.join(", ")} onChange={(e) => setProfile({ ...profile, target_locations: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="grad">
              Graduation date
            </label>
            <input id="grad" type="date" className="w-full rounded border px-2 py-1 text-sm" value={profile.grad_date ?? ""} onChange={(e) => setProfile({ ...profile, grad_date: e.target.value || null })} />
          </div>
        </div>

        <div className="flex flex-wrap gap-6 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={profile.remote_ok} onChange={(e) => setProfile({ ...profile, remote_ok: e.target.checked })} /> Open to remote
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={profile.needs_sponsorship} onChange={(e) => setProfile({ ...profile, needs_sponsorship: e.target.checked })} /> I need visa sponsorship
          </label>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="about">
            About / interests (optional, used for matching)
          </label>
          <textarea id="about" rows={3} className="w-full rounded border p-2 text-sm" value={profile.about_text ?? ""} onChange={(e) => setProfile({ ...profile, about_text: e.target.value || null })} />
        </div>
      </section>

      <section className="space-y-3 rounded-xl border bg-surface p-5 shadow-sm">
        <h2 className="font-medium">3. What gets embedded, then save</h2>
        <button type="button" disabled={busy} onClick={() => void doPreview()} className="rounded border px-3 py-1.5 text-sm">
          Show the exact text that will be embedded
        </button>
        {preview && <pre className="whitespace-pre-wrap rounded bg-canvas p-3 text-sm">{preview}</pre>}
        <div className="flex gap-3">
          <button type="button" disabled={busy} onClick={() => void save()} className="rounded bg-accent px-4 py-2 text-sm text-accent-ink disabled:opacity-40">
            Save profile
          </button>
          {saved && (
            <button type="button" disabled={busy} onClick={remove} className="rounded border border-bad/40 px-4 py-2 text-sm text-bad hover:bg-bad-bg">
              Delete my profile data
            </button>
          )}
        </div>
        {saved && <p className="text-xs text-subtle">Last saved {new Date(saved.updated_at).toLocaleString()}.</p>}
      </section>
    </div>
  );
}
