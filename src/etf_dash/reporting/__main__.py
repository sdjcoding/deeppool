"""CLI: build the public static report into an output directory.

    uv run python -m etf_dash.reporting --out site

Writes ``<out>/<slug>/index.html`` plus ``<out>/robots.txt`` and ``<out>/.nojekyll``
(for GitHub Pages). The ``<slug>`` is a stable unguessable token persisted in
``config/report.local.yaml`` (gitignored) so the public URL stays constant
across regenerations.
"""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path

import yaml

from etf_dash.analysis.strategies import load_strategies
from etf_dash.config import PROJECT_ROOT
from etf_dash.reporting.render import render_html
from etf_dash.reporting.report_data import gather_report
from etf_dash.repository.etf_repository import ETFRepository

SLUG_FILE = PROJECT_ROOT / "config" / "report.local.yaml"
STRATEGIES_YAML = PROJECT_ROOT / "config" / "strategies.yaml"


def get_or_create_slug(path: Path = SLUG_FILE) -> str:
    """Return the persisted report slug, generating + saving one if absent."""
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        slug = data.get("report_slug")
        if slug:
            return str(slug)
    slug = "r-" + secrets.token_urlsafe(16)
    path.write_text(yaml.safe_dump({"report_slug": slug}), encoding="utf-8")
    return slug


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the DeepPool public report")
    parser.add_argument("--out", default="site", help="output directory (default: site)")
    parser.add_argument("--slug", default=None, help="override the URL slug")
    parser.add_argument("--title", default="DeepPool 분석 리포트")
    args = parser.parse_args(argv)

    slug = args.slug or get_or_create_slug()
    out_root = Path(args.out)
    if not out_root.is_absolute():
        out_root = PROJECT_ROOT / out_root
    report_dir = out_root / slug
    report_dir.mkdir(parents=True, exist_ok=True)

    repo = ETFRepository()
    strategies = load_strategies(STRATEGIES_YAML)
    bundle = gather_report(repo, strategies)
    out_html = render_html(bundle, title=args.title)

    (report_dir / "index.html").write_text(out_html, encoding="utf-8")
    # Keep the whole site out of search engines and Jekyll's hands.
    (out_root / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (out_root / ".nojekyll").write_text("", encoding="utf-8")

    print(f"리포트 생성 완료: {report_dir / 'index.html'}")
    print(f"공개 경로(슬러그): /{slug}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
