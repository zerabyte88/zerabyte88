#!/usr/bin/env python3
"""Generate Zen Night / Sakura GitHub contribution graph SVGs (dark & light)."""

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
GRAPHQL_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            contributionLevel
            date
            weekday
          }
        }
      }
    }
  }
}
"""

LEVEL_MAP = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

THEMES = {
    "dark": {
        "bg": "#111428",
        "border": "#f9a8d4",
        "border_opacity": "0.22",
        "levels": ["#1b203b", "#4c1d3d", "#831843", "#db2777", "#f9a8d4"],
        "month_text": "#a5b4fc",
        "total_text": "#fbcfe8",
        "legend_text": "#a5b4fc",
    },
    "light": {
        "bg": "#f8fafc",
        "border": "#f9a8d4",
        "border_opacity": "0.55",
        "levels": ["#ebedf0", "#fce7f3", "#f9a8d4", "#ec4899", "#be185d"],
        "month_text": "#64748b",
        "total_text": "#9d174d",
        "legend_text": "#64748b",
    },
}

MONTH_ABBR = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def fetch_calendar(username: str, token: str) -> dict:
    payload = json.dumps({
        "query": GRAPHQL_QUERY,
        "variables": {"login": username},
    }).encode("utf-8")

    req = urllib.request.Request(
        GRAPHQL_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "zen-contrib-svg-generator",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub GraphQL HTTP {exc.code}: {err_body}") from exc

    if body.get("errors"):
        raise RuntimeError(f"GitHub GraphQL errors: {body['errors']}")

    user = (body.get("data") or {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user not found: {username}")

    return user["contributionsCollection"]["contributionCalendar"]


def build_demo_calendar() -> dict:
    """Deterministic 52-week sample calendar for local verification."""
    end_date = datetime.date(2026, 11, 20)
    days_since_sunday = (end_date.weekday() + 1) % 7
    start_date = end_date - datetime.timedelta(days=days_since_sunday + 52 * 7)

    weeks = []
    total = 0
    level_names = ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]
    counts = [0, 2, 5, 9, 15]

    for w in range(53):
        days = []
        for d in range(7):
            current = start_date + datetime.timedelta(days=w * 7 + d)
            if current > end_date:
                break
            seed = (w * 11 + d * 7 + (w ^ d)) % 17
            if seed < 6:
                lvl = 0
            elif seed < 10:
                lvl = 1
            elif seed < 13:
                lvl = 2
            elif seed < 15:
                lvl = 3
            else:
                lvl = 4
            cnt = counts[lvl]
            total += cnt
            days.append({
                "contributionCount": cnt,
                "contributionLevel": level_names[lvl],
                "date": current.isoformat(),
                "weekday": d,
            })
        if days:
            weeks.append({"contributionDays": days})

    return {"totalContributions": total, "weeks": weeks}


def render_svg(calendar: dict, theme_name: str) -> str:
    theme = THEMES[theme_name]
    weeks = calendar.get("weeks", [])[-53:]
    total = int(calendar.get("totalContributions", 0))

    width = 800
    height = 175
    cell = 11
    gap = 3
    step = cell + gap
    grid_w = max(1, len(weeks)) * step - gap
    origin_x = (width - grid_w) / 2.0
    origin_y = 40

    month_labels = []
    last_month = None
    last_label_x = -100.0
    for idx, week in enumerate(weeks):
        days = week.get("contributionDays") or []
        if not days:
            continue
        first_date = days[0].get("date", "")
        if len(first_date) >= 7:
            month_num = int(first_date[5:7])
            if month_num != last_month:
                x = origin_x + idx * step
                if x - last_label_x >= 34:
                    month_labels.append(
                        f'  <text x="{x:.1f}" y="28" fill="{theme["month_text"]}" '
                        f'font-size="10" font-weight="500">{MONTH_ABBR[month_num - 1]}</text>'
                    )
                    last_label_x = x
                last_month = month_num

    rects = []
    for w_idx, week in enumerate(weeks):
        x = origin_x + w_idx * step
        for day in week.get("contributionDays") or []:
            d_idx = int(day.get("weekday", 0))
            y = origin_y + d_idx * step
            lvl_key = day.get("contributionLevel", "NONE")
            lvl = LEVEL_MAP.get(lvl_key, 0)
            fill = theme["levels"][lvl]
            cnt = int(day.get("contributionCount", 0))
            date_str = escape(str(day.get("date", "")))
            rects.append(
                f'    <rect x="{x:.1f}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{fill}">'
                f'<title>{cnt} contributions on {date_str}</title></rect>'
            )

    right_edge = origin_x + grid_w
    more_x = right_edge
    legend_squares_start = right_edge - 34 - (5 * step - gap)
    less_x = legend_squares_start - 8

    legend_rects = []
    for i, color in enumerate(theme["levels"]):
        lx = legend_squares_start + i * step
        legend_rects.append(
            f'    <rect x="{lx:.1f}" y="146" width="{cell}" height="{cell}" rx="2.5" fill="{color}"/>'
        )

    total_label = f"{total:,} contributions in the last year"

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">',
        f'  <rect x="0.75" y="0.75" width="{width - 1.5}" height="{height - 1.5}" rx="14" '
        f'fill="{theme["bg"]}" stroke="{theme["border"]}" stroke-opacity="{theme["border_opacity"]}" stroke-width="1.5"/>',
        '  <g font-family="Verdana, Geneva, \'DejaVu Sans\', -apple-system, sans-serif">',
        *month_labels,
        '  </g>',
        '  <g>',
        *rects,
        '  </g>',
        '  <g font-family="Verdana, Geneva, \'DejaVu Sans\', -apple-system, sans-serif" font-size="10.5">',
        f'    <text x="{origin_x:.1f}" y="155" fill="{theme["total_text"]}" font-weight="600">{escape(total_label)}</text>',
        f'    <text x="{less_x:.1f}" y="155" fill="{theme["legend_text"]}" text-anchor="end">Less</text>',
        *legend_rects,
        f'    <text x="{more_x:.1f}" y="155" fill="{theme["legend_text"]}" text-anchor="end">More</text>',
        '  </g>',
        '</svg>',
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Zen Night / Sakura contribution graph SVGs.")
    parser.add_argument("--user", help="GitHub username to fetch contributions for.")
    parser.add_argument("--out-dir", default="dist", help="Output directory (default: dist).")
    parser.add_argument("--demo", action="store_true", help="Generate deterministic sample data without network/token.")
    args = parser.parse_args()

    if args.demo:
        calendar = build_demo_calendar()
    else:
        if not args.user:
            print("Error: --user is required unless --demo is set.", file=sys.stderr)
            return 1
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if not token:
            print("Error: GITHUB_TOKEN environment variable is required.", file=sys.stderr)
            return 1
        calendar = fetch_calendar(args.user, token)

    os.makedirs(args.out_dir, exist_ok=True)
    for variant in ("dark", "light"):
        svg_content = render_svg(calendar, variant)
        out_path = os.path.join(args.out_dir, f"zen-contrib-{variant}.svg")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(svg_content)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
