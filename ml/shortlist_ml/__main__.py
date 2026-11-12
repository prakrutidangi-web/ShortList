"""Phase 2 jobs: `python -m shortlist_ml enrich | embed | bench-device`. (Ingestion has its own CLI.)"""

import argparse
import sys
import time

from sqlalchemy import select

from shortlist_ml.config import get_settings
from shortlist_ml.db.models import Posting
from shortlist_ml.db.session import make_engine, make_session_factory


def cmd_enrich(_: argparse.Namespace) -> int:
    from shortlist_ml.skills.build import enrich_postings

    with make_session_factory(make_engine(get_settings().database_url))() as session:
        fam, sk = enrich_postings(session)
        session.commit()
    print(f"role_family changed on {fam} posting(s); skill set changed on {sk} posting(s)")
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    from shortlist_ml.embeddings.build import embed_open_postings
    from shortlist_ml.embeddings.encoder import SentenceTransformerEncoder, get_encoder

    s = get_settings()
    if args.device:
        s = s.model_copy(update={"embedding_device": args.device})
    t0 = time.perf_counter()
    encoder = get_encoder(s)
    load_s = time.perf_counter() - t0
    device = getattr(encoder, "device", "n/a")
    print(f"encoder={encoder.name} device={device} (model load {load_s:.1f}s)", flush=True)
    if isinstance(encoder, SentenceTransformerEncoder):
        encoder.batch_size = args.batch_size or s.embedding_batch_size

    def progress(done: int, total: int) -> None:
        print(f"  embedded {done}/{total}", flush=True)

    with make_session_factory(make_engine(s.database_url))() as session:
        stats = embed_open_postings(
            session, encoder, batch_size=args.batch_size or 64, limit=args.limit, on_batch=progress
        )
    rate = stats.embedded / stats.seconds if stats.seconds else 0.0
    print(
        f"open postings: {stats.open_postings}; embedded: {stats.embedded}; unchanged (skipped): {stats.unchanged}; "
        f"encode+write time: {stats.seconds:.1f}s ({rate:.1f} postings/s) on {device}"
    )
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    from shortlist_ml.embeddings.documents import posting_document
    from shortlist_ml.embeddings.encoder import SentenceTransformerEncoder

    with make_session_factory(make_engine(get_settings().database_url))() as session:
        posts = list(
            session.scalars(select(Posting).where(Posting.closed_at.is_(None)).limit(args.n))
        )
        docs = [
            posting_document(p.title, p.role_family, p.seniority, [], p.description_text)
            for p in posts
        ]
    for device in ("cpu", "mps"):
        try:
            enc = SentenceTransformerEncoder(device=device, batch_size=args.batch_size)
            enc.encode_documents(docs[:16])  # warm-up (kernel compilation, caches)
            t0 = time.perf_counter()
            enc.encode_documents(docs)
            dt = time.perf_counter() - t0
            print(
                f"{device:4}: {len(docs)} docs in {dt:.1f}s = {len(docs) / dt:.1f} docs/s (batch {args.batch_size})"
            )
        except Exception as exc:
            print(f"{device:4}: unavailable ({type(exc).__name__}: {exc})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m shortlist_ml")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("enrich", help="fill role_family and posting_skills").set_defaults(fn=cmd_enrich)
    p_e = sub.add_parser("embed", help="embed open postings (incremental)")
    p_e.add_argument("--limit", type=int)
    p_e.add_argument("--device", choices=["auto", "cpu", "mps", "cuda"])
    p_e.add_argument("--batch-size", type=int)
    p_e.set_defaults(fn=cmd_embed)
    p_b = sub.add_parser("bench-device", help="time the encoder on cpu vs mps")
    p_b.add_argument("--n", type=int, default=256)
    p_b.add_argument("--batch-size", type=int, default=32)
    p_b.set_defaults(fn=cmd_bench)
    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
