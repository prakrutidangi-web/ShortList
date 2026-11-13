"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, Meta, ProfileOut, Recommend, Result, ROLE_LABELS } from "@/lib/api";

type Filters = {
  location: string;
  remoteOnly: boolean;
  roleFamilies: string[];
  myRolesOnly: boolean;
  company: string;
  postedWithin: string;
  includeInterns: boolean;
  entryOnly: boolean;
  hideRestricted: boolean;
  collapse: boolean;
};

const DEFAULTS: Filters = {
  location: "",
  remoteOnly: false,
  roleFamilies: [],
  myRolesOnly: true,
  company: "",
  postedWithin: "",
  includeInterns: false,
  entryOnly: false,
  hideRestricted: false,
  collapse: true,
};

function toQuery(f: Filters, myRoles: string[]): string {
  const q = new URLSearchParams();
  if (f.location.trim()) q.set("location", f.location.trim());
  if (f.remoteOnly) q.set("remote_only", "true");
  const families = f.roleFamilies.length ? f.roleFamilies : f.myRolesOnly ? myRoles : [];
  families.forEach((r) => q.append("role_family", r));
  if (f.company) q.append("company", f.company);
  if (f.postedWithin) q.set("posted_within_days", f.postedWithin);
  if (f.includeInterns) q.set("include_interns", "true");
  if (f.entryOnly) q.set("entry_only", "true");
  if (f.hideRestricted) q.set("hide_restricted_sponsorship", "true");
  q.set("collapse_variants", String(f.collapse));
  q.set("limit", "50");
  return q.toString();
}

function Card({ r }: { r: Result }) {
  const [open, setOpen] = useState(false);
  const w = r.explanation.sponsorship_warning;
  return (
    <li className="rounded-xl border bg-surface p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold">{r.title}</h3>
          <p className="text-sm text-subtle">
            {r.company} · {r.location_raw ?? "location not stated"}
            {r.is_remote ? " · remote" : ""}
          </p>
        </div>
        <div className="text-right text-xs text-subtle">
          <div className="text-sm font-medium text-ink">score {r.score.toFixed(2)}</div>
          <div>#{r.position}</div>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
        {r.role_family && (
          <span className="rounded bg-muted px-2 py-0.5">{ROLE_LABELS[r.role_family] ?? r.role_family}</span>
        )}
        {r.is_entry_level ? (
          <span className="rounded bg-good-bg px-2 py-0.5 text-good">
            entry-level ({r.entry_evidence.rule}: “{r.entry_evidence.text}”)
          </span>
        ) : (
          <span className="rounded bg-muted px-2 py-0.5">{r.explanation.seniority}</span>
        )}
        {w && (
          <span
            className={`rounded px-2 py-0.5 ${w.level === "restricted" ? "bg-bad-bg text-bad" : "bg-warn-bg text-warn"}`}
            title={w.snippet ?? ""}
          >
            sponsorship: {w.level}
            {w.relevant_to_you ? " (you need it)" : ""}
          </span>
        )}
      </div>

      {r.explanation.matched_skills.length > 0 && (
        <p className="mt-2 text-sm">
          <span className="text-subtle">Matches your skills:</span> {r.explanation.matched_skills.join(", ")}
        </p>
      )}
      {r.also_listed_in.length > 0 && (
        <p className="mt-1 text-xs text-subtle">Also listed in: {r.also_listed_in.join(" · ")}</p>
      )}

      <div className="mt-3 flex items-center gap-4 text-sm">
        <a
          href={r.apply_url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded bg-accent px-3 py-1.5 font-medium text-accent-ink hover:opacity-90"
        >
          View &amp; apply on company site ↗
        </a>
        <button type="button" onClick={() => setOpen(!open)} className="text-subtle underline">
          {open ? "Hide why" : "Why this?"}
        </button>
      </div>

      {open && (
        <div className="mt-3 space-y-1 rounded bg-canvas p-3 text-sm">
          <p>
            <b>Seniority:</b> {r.explanation.seniority}
          </p>
          <p>
            <b>Location:</b> {r.explanation.location}
          </p>
          <p>
            <b>Posted:</b> {r.explanation.recency}
          </p>
          {r.explanation.missing_skills.length > 0 && (
            <p>
              <b>Also mentioned (you didn’t list):</b> {r.explanation.missing_skills.join(", ")}
            </p>
          )}
          {w?.snippet && (
            <p className="rounded bg-warn-bg p-2">
              <b>Sponsorship text:</b> “{w.snippet}”
            </p>
          )}
          <p className="pt-1 text-xs text-subtle">
            Score parts (0–1): {Object.entries(r.breakdown)
              .map(([k, v]) => `${k} ${v === null ? "n/a" : v.toFixed(2)}`)
              .join(" · ")}
          </p>
        </div>
      )}
    </li>
  );
}

export default function Feed() {
  const [filters, setFilters] = useState<Filters>(DEFAULTS);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [data, setData] = useState<Recommend | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [myRoles, setMyRoles] = useState<string[]>([]);
  const [rolesLoaded, setRolesLoaded] = useState(false);

  useEffect(() => {
    api<Meta>("/meta").then(setMeta).catch(() => setMeta(null));
    api<ProfileOut>("/profile")
      .then((p) => setMyRoles(p.target_roles))
      .catch(() => setMyRoles([]))
      .finally(() => setRolesLoaded(true));
  }, []);

  const load = useCallback(async (f: Filters, roles: string[]) => {
    setLoading(true);
    setError(null);
    try {
      setData(await api<Recommend>(`/recommend?${toQuery(f, roles)}`));
    } catch (e) {
      setData(null);
      setError(e instanceof ApiError ? { status: e.status, message: e.message } : { status: 0, message: "Cannot reach the API." });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (rolesLoaded) void load(filters, myRoles);
  }, [filters, load, myRoles, rolesLoaded]);

  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setFilters((f) => ({ ...f, [k]: v }));
  const toggleRole = (r: string) =>
    set("roleFamilies", filters.roleFamilies.includes(r) ? filters.roleFamilies.filter((x) => x !== r) : [...filters.roleFamilies, r]);

  return (
    <div className="grid gap-6 md:grid-cols-[240px_1fr]">
      <aside className="space-y-4 text-sm">
        <div>
          <label className="mb-1 block font-medium" htmlFor="loc">
            Location contains
          </label>
          <input id="loc" className="w-full rounded border px-2 py-1" value={filters.location} onChange={(e) => set("location", e.target.value)} placeholder="e.g. Seattle, CA, Canada" />
          <p className="mt-1 text-xs text-subtle">Postings with no stated location are kept.</p>
        </div>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={filters.remoteOnly} onChange={(e) => set("remoteOnly", e.target.checked)} /> Remote only
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={filters.myRolesOnly} onChange={(e) => set("myRolesOnly", e.target.checked)} /> Only my target role families
        </label>
        <fieldset>
          <legend className="mb-1 font-medium">Role family (overrides the above)</legend>
          {["software_engineering", "data_engineering", "ml_ai", "data_analytics", "other"].map((r) => (
            <label key={r} className="flex items-center gap-2">
              <input type="checkbox" checked={filters.roleFamilies.includes(r)} onChange={() => toggleRole(r)} /> {ROLE_LABELS[r]}
            </label>
          ))}
        </fieldset>
        <div>
          <label className="mb-1 block font-medium" htmlFor="co">
            Company
          </label>
          <select id="co" className="w-full rounded border px-2 py-1" value={filters.company} onChange={(e) => set("company", e.target.value)}>
            <option value="">All companies</option>
            {meta?.companies.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} ({c.open})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block font-medium" htmlFor="days">
            Posted within
          </label>
          <select id="days" className="w-full rounded border px-2 py-1" value={filters.postedWithin} onChange={(e) => set("postedWithin", e.target.value)}>
            <option value="">Any time</option>
            <option value="7">7 days</option>
            <option value="14">14 days</option>
            <option value="30">30 days</option>
            <option value="90">90 days</option>
          </select>
          <p className="mt-1 text-xs text-subtle">Uses the company-reported date.</p>
        </div>
        <div className="space-y-1 border-t pt-3">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={filters.includeInterns} onChange={(e) => set("includeInterns", e.target.checked)} /> Show internships
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={filters.entryOnly} onChange={(e) => set("entryOnly", e.target.checked)} /> Only flagged entry-level
          </label>
          <p className="text-xs text-subtle">The entry-level flag is a noisy heuristic; leave this off to avoid hiding good roles.</p>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={filters.hideRestricted} onChange={(e) => set("hideRestricted", e.target.checked)} /> Hide “no sponsorship” postings
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={filters.collapse} onChange={(e) => set("collapse", e.target.checked)} /> Merge same-title listings in other locations
          </label>
        </div>
        <button type="button" className="text-subtle underline" onClick={() => setFilters(DEFAULTS)}>
          Reset filters
        </button>
      </aside>

      <section>
        <div className="mb-3 rounded border border-warn/40 bg-warn-bg p-3 text-xs text-warn">
          Scores come from a hand-weighted scorer with <b>untuned</b> weights. They have not been measured against any baseline yet.
        </div>
        {loading && <p className="text-sm text-subtle">Loading…</p>}
        {error?.status === 409 && (
          <p className="rounded border bg-surface p-4">
            You don’t have a profile yet. <Link href="/profile" className="underline">Create one from your resume</Link> to see ranked postings.
          </p>
        )}
        {error && error.status !== 409 && <p className="rounded border border-bad/40 bg-bad-bg p-4 text-sm text-bad">{error.message}</p>}
        {data && (
          <>
            <p className="mb-3 text-sm text-subtle">
              {data.total_candidates} candidates retrieved (top {data.candidate_pool_cap} by similarity, after merging duplicates) · showing {data.results.length} · {data.timing_ms} ms · request {data.request_id.slice(0, 8)}
              {data.notes.length > 0 && <span className="block text-xs text-subtle">{data.notes.join("; ")}</span>}
            </p>
            <ul className="space-y-3">
              {data.results.map((r) => (
                <Card key={r.posting_id} r={r} />
              ))}
            </ul>
            {data.results.length === 0 && <p className="rounded border bg-surface p-4 text-sm">No postings match these filters.</p>}
          </>
        )}
      </section>
    </div>
  );
}
