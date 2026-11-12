type Health = { status: string; db: string };

// Server-side fetch so the browser never needs CORS; API_URL is the in-network address under compose.
async function getHealth(): Promise<Health | null> {
  const base = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${base}/health`, { cache: "no-store" });
    return res.ok ? ((await res.json()) as Health) : null;
  } catch {
    return null;
  }
}

export const dynamic = "force-dynamic";

export default async function Home() {
  const health = await getHealth();
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-3xl font-semibold">Shortlist</h1>
      <p className="mt-2 text-gray-600">
        Personalized ranking for new-grad job postings. Phase 0 scaffold: no feed yet.
      </p>
      <p className="mt-6 text-sm" data-testid="api-status">
        API: {health ? `${health.status} (db: ${health.db})` : "unreachable"}
      </p>
    </main>
  );
}
