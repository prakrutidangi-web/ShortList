export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ProfileIn = {
  skills: string[];
  target_roles: string[];
  target_locations: string[];
  remote_ok: boolean;
  grad_date: string | null;
  needs_sponsorship: boolean;
  about_text: string | null;
};
export type ProfileOut = ProfileIn & { profile_document: string; updated_at: string };
export type Suggestion = {
  source: string;
  characters_read: number;
  skills: string[];
  grad_date: string | null;
  grad_date_evidence: string | null;
  note: string;
};
export type SponsorshipWarning = { level: string; snippet: string | null; relevant_to_you: boolean };
export type Explanation = {
  matched_skills: string[];
  missing_skills: string[];
  skill_coverage: number | null;
  seniority: string;
  location: string;
  recency: string;
  sponsorship_warning: SponsorshipWarning | null;
};
export type Result = {
  position: number;
  posting_id: number;
  company: string;
  title: string;
  location_raw: string | null;
  is_remote: boolean | null;
  role_family: string | null;
  seniority: string;
  is_entry_level: boolean;
  entry_evidence: { rule: string | null; text: string | null };
  apply_url: string;
  posted_at: string | null;
  score: number;
  breakdown: Record<string, number | null>;
  explanation: Explanation;
  also_listed_in: string[];
};
export type Recommend = {
  request_id: string;
  weights_version: string;
  weights: Record<string, number>;
  disclaimer: string;
  total_candidates: number;
  candidate_pool_cap: number;
  notes: string[];
  timing_ms: number;
  results: Result[];
};
export type Meta = {
  total_open: number;
  role_families: string[];
  companies: { name: string; open: number }[];
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function readError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    const d = body.detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && "message" in d) return String((d as { message: unknown }).message);
    return JSON.stringify(d ?? body);
  } catch {
    return res.statusText;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  return (await res.json()) as T;
}

export const ROLE_LABELS: Record<string, string> = {
  software_engineering: "Software engineering",
  data_engineering: "Data engineering",
  ml_ai: "ML / AI",
  data_analytics: "Data analytics",
  other: "Other",
};
