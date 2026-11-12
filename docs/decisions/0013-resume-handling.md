# Resumes are parsed in memory; only confirmed, derived data is stored

**Status:** accepted

**Context:** A resume contains names, contact details and work history. The product needs skills and a graduation date, and a vector for retrieval.

**Decision:** Upload (text-based PDF or pasted text; no OCR) is parsed in memory with limits: 5 MB, '%PDF-' magic bytes, 10 pages, 15 s timeout, and a scanned/image PDF is rejected with a clear message. The raw file and text are never written to disk or the database and never logged (file names too). The endpoint returns SUGGESTIONS only (dictionary skills and a graduation date with its matched snippet); nothing is saved until the user reviews and confirms. Names, emails, phone numbers and addresses are never extracted. What is stored: confirmed skills, target roles, target locations, remote/sponsorship preferences, an optional user-typed 'about' text, the exact profile document that is embedded (shown to the user before saving), and its embedding. Embedding runs locally; no resume text goes to any third-party service. DELETE /profile removes the profile row, all derived fields and the embedding; tests prove the rows are gone and public posting data is untouched. A logging filter additionally redacts email/phone-shaped strings, and a test uploads a synthetic resume and asserts none of its PII appears in logs or storage.

**Alternatives:** Storing the raw resume (more convenient, much higher risk); embedding the whole resume text (better recall, but the vector of sensitive text becomes a hard-to-inspect copy of it); a third-party parsing API (rejected: no resume text leaves the machine).

**Consequences:** Retrieval quality is limited by the structured profile document (skills list plus optional about-text), not the full resume prose. An embedding derived from the profile is treated as sensitive and deleted with it. pypdf is a pure-Python parser; its timeout runs in a worker thread that cannot be force-killed, so a pathological PDF could still use CPU after the request times out. Interaction logs (Phase 3) must be added to the delete path.
