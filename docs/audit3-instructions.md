# Blind audit sample 3: how to label

File to label: `audit3-blind-sample.csv` (50 postings, shuffled, **no rule output**: not the entry-level flag, the rule that fired,
the seniority, the parsed city/region/country, or the sponsorship value). The answers are in a local key file the assistant has not shown you.

Fill these columns in a COPY of the CSV (keep the `n` column). Open the `apply_url` if the excerpt is not enough.

| Column | What to enter |
|---|---|
| `entry_label` | `entry` = a new grad / 0-1 year candidate clearly can apply (explicit new-grad or early-career, "0-1 years", or no experience required). `maybe` = asks for roughly 1-3 years, or you cannot tell. `not` = needs more than ~3 years, senior/manager, or an internship (interns are `not`; the target is full-time). |
| `city`, `region`, `country` | What the **location text itself says**, using only the first location if there are several. Region = US state or Canadian province as a 2-letter code (CA, NY, ON). Country = 2-letter ISO code (US, CA, GB). Leave a field **blank if the text does not say it** (do not use outside geography knowledge, e.g. "Seattle" alone has no country; "Seattle, Washington" is WA / US). "Hybrid" or "Remote" alone: all blank. |
| `sponsorship_label` | Optional: `restricted`, `offered` or `unclear`, only if you read the posting. |
| `notes` | Optional. |

Then run (the key and the assistant's sealed labels stay local in `data/processed/`):

```
uv run python -m shortlist_ml.ingest audit-compare --key data/processed/audit3-key.csv --labels YOUR_LABELS.csv \
    --other-labels data/processed/audit3-assistant-labels.csv
```

**Please do not open `data/processed/audit3-key.csv` or `audit3-assistant-labels.csv` until you have finished labeling.**
The assistant's labels were written before seeing your labels or the rule output, and are sealed by this hash:
`SHA256 29bd8326ccee03b02de26688fdeb065241a0a5a97ac386eba1065eeb1f42c936` (`shasum -a 256 data/processed/audit3-assistant-labels.csv`).
The comparison reports precision with confidence intervals for both labelers, location accuracy, and where you and the assistant disagree.
