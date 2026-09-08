"""Command line: ``python -m csfcheck <command>``."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_PORT = 23180


def _engine():
    from .engine import Engine

    return Engine.default()


def cmd_export(args) -> int:
    from .engine import AnswerError
    from .samples import load_answers
    from .workbook import export_workbook

    engine = _engine()
    org = load_answers(args.answers)
    profile = engine.bank.normalise_profile(org.profile)
    try:
        engine.check_answers(profile, org.answers)
    except AnswerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    result = engine.assess(profile, org.answers)
    out = export_workbook(args.output, engine, result, org.answers, org.evidence, org.name)
    t = result.totals
    print(
        f"{org.name}: asked {t['questions_asked']} of {t['questions_in_bank']} questions "
        f"({t['skipped_pct']}% skipped), {t['subcategories_assessed']} subcategories assessed, "
        f"{len(result.actions)} actions"
    )
    for a in result.actions[: args.top]:
        print(f"  {a.rank:>2}. {a.subcategory:<9} {a.rating:<8} {a.cost_band:<6} {a.what_to_do[:80]}")
    print(f"wrote {out}")
    return 0 if result.complete or args.allow_incomplete else 1


def cmd_stats(args) -> int:
    from .samples import load_answers

    engine = _engine()
    rows = []
    for path in args.answers:
        org = load_answers(path)
        t = engine.assess(org.profile, org.answers).totals
        rows.append((org.name, t))
        print(
            f"{org.name:<40} asked {t['questions_asked']:>3}/{t['questions_in_bank']}  "
            f"profile-skipped {t['skipped_profile']:>2}  follow-ups skipped {t['skipped_follow_up']:>2}  "
            f"skipped {t['skipped_pct']:>5}%  excluded subcats {t['subcategories_excluded']}"
        )
    if rows:
        mean = sum(t["skipped_pct"] for _, t in rows) / len(rows)
        print(f"mean skipped: {mean:.1f}%")
    return 0


def cmd_check(args) -> int:
    from .catalog import default_catalog
    from .model import default_targets

    cat = default_catalog()
    engine = _engine()
    targets = default_targets()
    tiers = {t: sum(v == t for v in targets.tiers.values()) for t in (1, 2, 3)}
    print(f"{cat.document} {cat.version}: {len(cat.functions)} functions, {len(cat.categories)} categories, "
          f"{len(cat.subcategories)} subcategories, "
          f"{sum(len(s.examples) for s in cat.subcategories.values())} implementation examples")
    print(f"export SHA-256 {cat.sha256} (matches vendored checksum)")
    print(f"question bank: {len(engine.bank.questions)} questions, {len(engine.bank.exclusions)} exclusion rules, "
          f"coverage checked over {2 ** len(engine.bank.flags)} profiles")
    print(f"Quick-Start targets: {tiers[3]} cited (3), {tiers[2]} by category (2), {tiers[1]} baseline (1)")
    return 0


def _database_url(args) -> str | None:
    return args.database_url or os.environ.get("CSFCHECK_DATABASE_URL")


def cmd_load_csf(args) -> int:
    from .db import load_core, make_engine

    url = _database_url(args)
    if not url:
        print("error: pass --database-url or set CSFCHECK_DATABASE_URL", file=sys.stderr)
        return 2
    counts = load_core(make_engine(url))
    print(", ".join(f"{v} {k}" for k, v in counts.items()))
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .api import create_app
    from .devdb import temporary_postgres

    if args.temp_db:
        with temporary_postgres() as url:
            print(f"using temporary PostgreSQL at {url}")
            uvicorn.run(create_app(url), host=args.host, port=args.port)
        return 0
    url = _database_url(args)
    if not url:
        print("error: pass --database-url, set CSFCHECK_DATABASE_URL or use --temp-db", file=sys.stderr)
        return 2
    uvicorn.run(create_app(url), host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="csfcheck", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("export", help="score an answers file and write the Excel workbook")
    p.add_argument("answers", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--top", type=int, default=5, help="actions to print (default 5)")
    p.add_argument("--allow-incomplete", action="store_true")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("stats", help="questions asked and skipped for answers files")
    p.add_argument("answers", type=Path, nargs="+")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("check", help="verify the CSF export checksum and the question bank")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("load-csf", help="import the CSF 2.0 core into PostgreSQL")
    p.add_argument("--database-url")
    p.set_defaults(func=cmd_load_csf)

    p = sub.add_parser("serve", help="run the API")
    p.add_argument("--database-url")
    p.add_argument("--temp-db", action="store_true", help="start a throwaway local PostgreSQL")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)
