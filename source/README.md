# NTXEC District Legislative Updates

One weekly master issue, published under each subscribing district's brand. Content is identical for every district; only the logo, colors, fonts and attribution change.

## Weekly workflow

1. Draft and finalize the master copy in the Claude Doc for that week.
2. Save the final copy as `content/YYYY-MM-DD.md` (the Friday issue date), with front matter: `title`, `issue_date`, `week_label`, `preheader` (under 150 characters).
3. Run `python3 build.py content/YYYY-MM-DD.md` to build every district, or add a slug to build one.
4. Publish `dist/` to the host for updates.ntxec.org.
5. Send each district its handoff: the web link for the board PDF, plus `email.html` and `email.txt` for when the district sends it.

## Output per district

| Path | Use |
| --- | --- |
| `dist/<slug>/<date>/index.html` | Web version. This is the link that goes in the board PDF. |
| `dist/<slug>/<date>/email.html` | Send-ready email: inline styles, table layout, hidden preheader. |
| `dist/<slug>/<date>/email.txt` | Plain-text version for platforms that need one. |
| `dist/<slug>/index.html` | Archive of every issue for that district. |

Web pages are marked `noindex` so search engines skip them.

## Customizing one district's copy

Everything stays shared unless a district has an override file next to the master issue: `content/<issue date>.<slug>.md`, such as `content/2026-11-13.dallas-isd.md`. A full example is in `examples/`.

| Directive | Effect |
| --- | --- |
| `@@ note top` | Labeled callout above the first section ("A note from Dallas ISD") |
| `@@ note bottom` | Labeled callout above Sources |
| `@@ note after: School Finance` | Labeled callout at the end of that section |
| `@@ add before: Looking Ahead` | New section; include its own `##` heading |
| `@@ add after: School Finance` | New section; include its own `##` heading |
| `@@ replace: Property Tax Relief` | Replaces the section; the original heading stays unless you write a new one |
| `@@ omit: Education Savings Accounts` | Drops the section for that district |

A `preheader:` line in the file's front matter replaces the preheader for that district only.

Section names match the master's `##` headings. A name that matches nothing stops the build and lists the real section names, so a renamed heading never silently drops a district's custom copy. Each customized build writes `changes.txt` beside the district's files listing exactly how it differs from the master. Review that before publishing.

Override files apply to one issue only. Nothing carries forward to the next week unless you copy the file.

Prefer notes over replacements. Notes are labeled as the district's own voice, which keeps them visibly separate from the shared analysis. Hold `replace` and `add` copy to the same sourcing and neutrality rules as the master.

## Adding a district

Copy `brands/dallas-isd.json` to `brands/<slug>.json` and change the name, logo URL, colors and `web_base_url`. `dashboard_url` and `dashboard_label` add a button after the closing that links to the district's branded bill dashboard (`https://dashboard.ntxec.org/?d=<code>`, codes listed in the ntxec-dashboard repo README); leave `dashboard_url` empty for no button. `attribution` is optional; leave it empty for no attribution line (the footer then shows the update's name). Check that link text color has at least 4.5:1 contrast on white; many district accent colors need a darker shade for links.

## Rules for the master copy

- No district names or district-specific framing. Every district receives the same text.
- Primary sources only: bill links go to Texas Legislature Online; hearing items cite the official broadcast; agency items cite the agency's own document.
- Invited testimony only. Leave out actions by a party or group of lawmakers acting alone unless they come from someone positioned to drive them.
- Avoid dashes in drafted text.

## Hosting

Published from the GitHub repo drstockton-ntxec/ntxec-updates via GitHub Pages at https://updates.ntxec.org (DNS: CNAME `updates` to `drstockton-ntxec.github.io`). Built pages sit at the repo root; this build system is kept in the repo's `source/` folder. Each week: build, copy `dist/*` to the repo root, commit, push.
