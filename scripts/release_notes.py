"""Print the CHANGELOG.md section of one version.

Used by the publish workflow twice: the whole section for the GitHub release notes (--limit 0), and a copy
that fits Orca Cloud's changelog field (4000 characters; default limit 3900 UTF-8 bytes) cut at a line
boundary, with a pointer to the full text. Exits non-zero when the version has no section or the section
is empty, so a release without notes cannot ship.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def section(changelog, version):
    """The text under `## [version]` up to the next `## [` heading, stripped; None when there is no such heading."""
    lines = changelog.splitlines()
    heading = re.compile(r"^## \[%s\](?: - \d{4}-\d{2}-\d{2})?\s*$" % re.escape(version))
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        return None
    body = []
    for line in lines[start + 1:]:
        if line.startswith("## ["):
            break
        body.append(line)
    return "\n".join(body).strip()


def fit(text, limit, footer):
    """`text` unchanged when it fits `limit` UTF-8 bytes; otherwise whole lines plus `footer`. limit 0 = no limit."""
    if limit <= 0 or len(text.encode("utf-8")) <= limit:
        return text
    kept = text.splitlines()
    while kept and len(("\n".join(kept).rstrip() + footer).encode("utf-8")) > limit:
        kept.pop()
    if not kept:
        raise SystemExit("release notes: the first line alone does not fit %d bytes" % limit)
    return "\n".join(kept).rstrip() + footer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="without the leading v, e.g. 0.2.0")
    parser.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    parser.add_argument("--limit", type=int, default=3900)
    parser.add_argument("--url", default="", help="where the full notes live (the GitHub release page)")
    args = parser.parse_args(argv)
    text = section(args.changelog.read_text("utf-8"), args.version.lstrip("v"))
    if not text:
        print("CHANGELOG.md has no non-empty section for %s" % args.version, file=sys.stderr)
        return 1
    footer = "\n\n... Full notes: %s" % args.url if args.url else "\n\n... Full notes: CHANGELOG.md in the release source."
    print(fit(text, args.limit, footer))
    return 0


if __name__ == "__main__":
    sys.exit(main())
