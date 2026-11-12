"""Build district-branded legislative updates from one master issue.

Usage:
    python3 build.py content/2026-11-13.md            # every brand kit in brands/
    python3 build.py content/2026-11-13.md dallas-isd # one district

For each district, writes to dist/<slug>/:
    <issue_date>/index.html   web version (the link that goes in the board PDF)
    <issue_date>/email.html   send-ready email HTML (inline styles, table layout)
    <issue_date>/email.txt    plain-text version
    <issue_date>/changes.txt  what this district's version changes from the master (if anything)
    index.html                archive page listing every issue built so far
"""

import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

import markdown
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
BRANDS = ROOT / "brands"
DIST = ROOT / "dist"


# ---------- content ----------

def split_front(text):
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, m.group(2)


def load_issue(path):
    text = Path(path).read_text(encoding="utf-8")
    meta, body = split_front(text)
    if not meta:
        sys.exit("Issue file needs front matter between --- lines.")
    for key in ("title", "issue_date", "week_label", "preheader"):
        if not meta.get(key):
            sys.exit(f"Front matter is missing '{key}'.")
    check_preheader(meta["preheader"], "master issue")
    meta["date"] = dt.date.fromisoformat(meta["issue_date"])
    meta["body_md"] = body.strip()
    meta["path"] = Path(path)
    return meta


def check_preheader(text, where):
    if len(text) >= 150:
        sys.exit(f"Preheader in {where} is {len(text)} characters; keep it under 150.")


# ---------- per-district overrides ----------
#
# Optional file next to the master issue: content/<issue>.<slug>.md
# e.g. content/2026-11-13.dallas-isd.md. Everything not named in it stays shared.
#
#   ---
#   preheader: optional district preheader (under 150 characters)
#   ---
#   @@ note top                       callout box above the first section
#   @@ note bottom                    callout box after the last section
#   @@ note after: School Finance     callout box at the end of that section
#   @@ add before: Looking Ahead      new section; include its own ## heading
#   @@ add after: School Finance      new section; include its own ## heading
#   @@ replace: Property Tax Relief   replaces the section; ## heading optional
#   @@ omit: Education Savings Accounts
#
# Section names match the master's ## headings exactly (case does not matter).
# A name that matches nothing stops the build, so a renamed heading never
# silently drops a district's custom copy.

DIRECTIVE = re.compile(
    r"^@@\s*(note|add|replace|omit)\s*(top|bottom|before|after)?\s*:?\s*(.*?)\s*$", re.I
)


def split_sections(body_md):
    """Return [(heading or None, markdown)] in order; heading None = text before the first ##."""
    sections, current_head, buf = [], None, []
    for line in body_md.splitlines():
        if line.startswith("## "):
            if current_head is not None or "".join(buf).strip():
                sections.append((current_head, "\n".join(buf).strip()))
            current_head, buf = line[3:].strip(), [line]
        else:
            buf.append(line)
    sections.append((current_head, "\n".join(buf).strip()))
    return sections


def load_overrides(issue, slug):
    path = issue["path"].with_name(f"{issue['path'].stem}.{slug}.md")
    if not path.exists():
        return None
    meta, body = split_front(path.read_text(encoding="utf-8"))
    if meta.get("preheader"):
        check_preheader(meta["preheader"], path.name)
    blocks, current = [], None
    for line in body.splitlines():
        m = DIRECTIVE.match(line)
        if m:
            action, where, target = m.group(1).lower(), (m.group(2) or "").lower(), m.group(3)
            current = {"action": action, "where": where, "target": target, "lines": []}
            blocks.append(current)
        elif current is not None:
            current["lines"].append(line)
        elif line.strip():
            sys.exit(f"{path.name}: text before the first @@ directive: {line[:60]!r}")
    for blk in blocks:
        blk["md"] = "\n".join(blk["lines"]).strip()
        a, w = blk["action"], blk["where"]
        if a == "note" and w not in ("top", "bottom", "after"):
            sys.exit(f"{path.name}: use '@@ note top', '@@ note bottom' or '@@ note after: <Section>'.")
        if a == "add" and w not in ("before", "after"):
            sys.exit(f"{path.name}: use '@@ add before: <Section>' or '@@ add after: <Section>'.")
        if a in ("replace", "omit", "add") or w == "after":
            if not blk["target"]:
                sys.exit(f"{path.name}: '@@ {a} {w}' needs a section name.")
        if a in ("note", "add", "replace") and not blk["md"]:
            sys.exit(f"{path.name}: '@@ {a} {w} {blk['target']}' has no text under it.")
    return {"file": path.name, "preheader": meta.get("preheader"), "blocks": blocks}


def note_md(text, b):
    label = b.get("note_label") or f"A note from {b['district_name']}"
    return f'<div class="district-note" markdown="1">\n\n**{label}**\n\n{text}\n\n</div>'


def apply_overrides(issue, ov, b):
    """Return (body_md, preheader, changes) for one district."""
    sections = split_sections(issue["body_md"])
    index = {h.lower(): i for i, (h, _) in enumerate(sections) if h}
    before = {i: [] for i in range(len(sections))}
    after = {i: [] for i in range(len(sections))}
    top, bottom, changes = [], [], []
    replaced, omitted = {}, set()

    def find(name, blk):
        i = index.get(name.lower())
        if i is None:
            known = ", ".join(h for h, _ in sections if h)
            sys.exit(f"{ov['file']}: no section named '{name}' "
                     f"(for '@@ {blk['action']} {blk['where']}'). Sections are: {known}")
        return i

    for blk in ov["blocks"]:
        a, w, t, md = blk["action"], blk["where"], blk["target"], blk["md"]
        if a == "note" and w == "top":
            top.append(note_md(md, b)); changes.append("Added a district note at the top")
        elif a == "note" and w == "bottom":
            bottom.append(note_md(md, b)); changes.append("Added a district note at the bottom")
        elif a == "note":
            i = find(t, blk); after[i].append(note_md(md, b))
            changes.append(f"Added a district note to '{sections[i][0]}'")
        elif a == "add":
            i = find(t, blk)
            if not md.lstrip().startswith("## "):
                sys.exit(f"{ov['file']}: '@@ add {w}: {t}' needs its own ## heading.")
            (before if w == "before" else after)[i].append(md)
            changes.append(f"Added section '{md.lstrip()[3:].splitlines()[0].strip()}' {w} '{sections[i][0]}'")
        elif a == "replace":
            i = find(t, blk)
            if i in omitted:
                sys.exit(f"{ov['file']}: '{t}' is both replaced and omitted.")
            replaced[i] = md if md.lstrip().startswith("## ") else f"## {sections[i][0]}\n\n{md}"
            changes.append(f"Replaced section '{sections[i][0]}'")
        elif a == "omit":
            i = find(t, blk)
            if i in replaced:
                sys.exit(f"{ov['file']}: '{t}' is both replaced and omitted.")
            omitted.add(i); changes.append(f"Omitted section '{sections[i][0]}'")

    # Notes at the top sit under the first section's heading position: before everything.
    parts = list(top)
    for i, (head, md) in enumerate(sections):
        parts += before[i]
        if i not in omitted:
            parts.append(replaced.get(i, md))
        parts += after[i]
    # Bottom notes go before Sources if the issue has one, else at the very end.
    src = index.get("sources")
    if bottom and src is not None and src not in omitted:
        src_md = replaced.get(src, sections[src][1])
        pos = parts.index(src_md)
        parts[pos:pos] = bottom
    else:
        parts += bottom
    preheader = ov.get("preheader") or issue["preheader"]
    if ov.get("preheader"):
        changes.append("Used a district preheader")
    return "\n\n".join(p for p in parts if p.strip()), preheader, changes


def long_date(d):
    return f"{d.strftime('%B')} {d.day}, {d.year}"


# ---------- email HTML ----------

def style_for_email(body_html, b):
    c, font = b["colors"], b["font_stack"]
    soup = BeautifulSoup(body_html, "html.parser")
    styles = {
        "h2": f"margin:32px 0 12px;padding:0 0 8px;font-family:{font};font-size:20px;line-height:26px;font-weight:bold;color:{c['primary']};border-bottom:2px solid {c['accent']};",
        "p": f"margin:0 0 14px;font-family:{font};font-size:15px;line-height:23px;color:{c['text']};",
        "ul": "margin:0 0 14px;padding:0 0 0 22px;",
        "ol": "margin:0 0 14px;padding:0 0 0 22px;",
        "li": f"margin:0 0 8px;font-family:{font};font-size:15px;line-height:23px;color:{c['text']};",
        "strong": f"font-weight:bold;color:{c['primary']};",
        "a": f"color:{c['accent_text']};text-decoration:underline;",
    }
    for tag, css in styles.items():
        for el in soup.find_all(tag):
            el["style"] = css
    for note in soup.find_all("div", class_="district-note"):
        box = soup.new_tag("table", attrs={
            "role": "presentation", "width": "100%", "cellpadding": "0", "cellspacing": "0", "border": "0",
            "style": "width:100%;border-collapse:collapse;margin:4px 0 18px;"})
        tr = soup.new_tag("tr"); td = soup.new_tag("td", attrs={
            "style": f"padding:16px 18px 4px;background:{c['band']};border-left:4px solid {c['highlight']};"})
        for child in list(note.contents):
            td.append(child.extract())
        tr.append(td); box.append(tr); note.replace_with(box)
    first_h2 = soup.find("h2")
    if first_h2:
        first_h2["style"] = first_h2["style"].replace("margin:32px", "margin:8px")
    for table in soup.find_all("table"):
        table["width"] = "100%"
        table["cellpadding"] = "0"
        table["cellspacing"] = "0"
        table["border"] = "0"
        table["style"] = f"width:100%;border-collapse:collapse;margin:4px 0 18px;font-family:{font};"
        for th in table.find_all("th"):
            th["align"] = "left"
            th["style"] = f"padding:8px 10px;background:{c['primary']};color:#FFFFFF;font-family:{font};font-size:13px;line-height:18px;font-weight:bold;text-align:left;"
        for i, tr in enumerate(table.find("tbody").find_all("tr") if table.find("tbody") else []):
            bg = c["band"] if i % 2 else "#FFFFFF"
            for td in tr.find_all("td"):
                td["style"] = f"padding:8px 10px;background:{bg};border-bottom:1px solid {c['rule']};color:{c['text']};font-family:{font};font-size:14px;line-height:20px;vertical-align:top;"
    return str(soup)


def build_email(issue, b, web_url):
    c, font = b["colors"], b["font_stack"]
    body = style_for_email(markdown.markdown(issue["body_md"], extensions=["tables", "md_in_html"]), b)
    pre = html.escape(issue["preheader"])
    footer_text = b.get("attribution") or f"{b['district_name']} {b['update_name']}"
    footer_line = f'<p style="margin:0;font-family:{font};font-size:13px;line-height:19px;color:{c["muted"]};">{html.escape(footer_text)}</p>'
    title = html.escape(f"{b['district_name']} {b['update_name']}: {issue['week_label']}")
    contact = (
        f'<p style="margin:0 0 8px;font-family:{font};font-size:13px;line-height:19px;color:{c["muted"]};">{html.escape(b["contact_line"])}</p>'
        if b.get("contact_line") else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{title}</title>
<style>
  @media only screen and (max-width:620px) {{
    .container {{ width:100% !important; }}
    .px {{ padding-left:20px !important; padding-right:20px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:{c['band']};">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:{c['band']};">{pre}&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{c['band']};">
<tr><td align="center" style="padding:24px 10px;">
  <table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:#FFFFFF;">
    <tr><td class="px" align="left" style="padding:28px 40px 20px;background:#FFFFFF;">
      <img src="{html.escape(b['logo_url'])}" width="{b['logo_width']}" alt="{html.escape(b['logo_alt'])}" style="display:block;width:{b['logo_width']}px;max-width:100%;height:auto;border:0;">
    </td></tr>
    <tr><td class="px" style="padding:20px 40px;background:{c['primary']};">
      <p style="margin:0 0 4px;font-family:{font};font-size:13px;line-height:18px;letter-spacing:1px;text-transform:uppercase;color:#FFFFFF;">{html.escape(b['update_name'])}</p>
      <h1 style="margin:0;font-family:{font};font-size:26px;line-height:32px;font-weight:bold;color:#FFFFFF;">{html.escape(issue['week_label'])}</h1>
    </td></tr>
    <tr><td style="height:4px;line-height:4px;font-size:4px;background:{c['accent']};">&nbsp;</td></tr>
    <tr><td class="px" style="padding:24px 40px 8px;">
      <p style="margin:0 0 4px;font-family:{font};font-size:13px;line-height:19px;color:{c['muted']};">{long_date(issue['date'])} &middot; <a href="{html.escape(web_url)}" style="color:{c['accent_text']};text-decoration:underline;">View this update online</a></p>
      {body}
    </td></tr>
    <tr><td class="px" style="padding:20px 40px 28px;border-top:1px solid {c['rule']};">
      {contact}
      {footer_line}
    </td></tr>
  </table>
</td></tr>
</table>
</body>
</html>
"""


# ---------- plain text ----------

def build_text(issue, b, web_url):
    md = issue["body_md"]
    md = re.sub(r'<div class="district-note" markdown="1">\s*', "", md)
    md = md.replace("</div>", "")
    md = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", md)
    md = re.sub(r"\*\*([^*]+)\*\*", r"\1", md)
    lines = []
    for line in md.splitlines():
        if line.startswith("## "):
            head = line[3:].upper()
            lines += ["", head, "-" * len(head)]
        elif re.match(r"^\|\s*-", line):
            continue
        elif line.startswith("|"):
            cells = [x.strip() for x in line.strip("|").split("|")]
            lines.append("  " + "  |  ".join(cells))
        else:
            lines.append(line)
    header = [
        f"{b['district_name'].upper()} {b['update_name'].upper()}",
        issue["week_label"],
        long_date(issue["date"]),
        f"View online: {web_url}",
    ]
    footer = ["", "--"]
    if b.get("contact_line"):
        footer.append(b["contact_line"])
    if b.get("attribution"):
        footer.append(b["attribution"])
    return "\n".join(header + lines + footer).replace("\n\n\n", "\n\n").strip() + "\n"


# ---------- web page ----------

WEB_CSS = """
:root {{ --primary:{primary}; --accent:{accent}; --link:{accent_text}; --text:{text}; --muted:{muted}; --rule:{rule}; --band:{band}; }}
* {{ box-sizing:border-box; }}
html {{ -webkit-text-size-adjust:100%; }}
body {{ margin:0; background:var(--band); color:var(--text); font-family:{font}; font-size:17px; line-height:1.6; }}
.wrap {{ max-width:760px; margin:0 auto; background:#fff; min-height:100vh; }}
header .logo {{ padding:28px 40px 20px; }}
header .logo img {{ display:block; width:{logo_width}px; max-width:60%; height:auto; }}
header .band {{ background:var(--primary); color:#fff; padding:22px 40px; border-bottom:5px solid var(--accent); }}
header .eyebrow {{ margin:0 0 4px; font-size:13px; letter-spacing:.08em; text-transform:uppercase; }}
header h1 {{ margin:0; font-size:30px; line-height:1.2; }}
main {{ padding:24px 40px 8px; }}
.meta {{ color:var(--muted); font-size:14px; margin:0 0 8px; }}
h2 {{ color:var(--primary); font-size:22px; line-height:1.3; margin:36px 0 12px; padding-bottom:8px; border-bottom:2px solid var(--accent); }}
main > h2:first-of-type {{ margin-top:12px; }}
p, li {{ margin:0 0 14px; }}
ul {{ padding-left:22px; margin:0 0 14px; }}
strong {{ color:var(--primary); }}
a {{ color:var(--link); text-underline-offset:2px; }}
a:hover {{ color:var(--primary); }}
.table-scroll {{ overflow-x:auto; margin:4px 0 20px; }}
table {{ width:100%; border-collapse:collapse; font-size:15px; line-height:1.4; }}
th {{ background:var(--primary); color:#fff; text-align:left; padding:9px 12px; font-weight:bold; }}
td {{ padding:9px 12px; border-bottom:1px solid var(--rule); vertical-align:top; }}
tbody tr:nth-child(even) td {{ background:var(--band); }}
footer {{ padding:20px 40px 36px; border-top:1px solid var(--rule); color:var(--muted); font-size:14px; }}
footer p {{ margin:0 0 6px; }}
.district-note {{ background:var(--band); border-left:4px solid {highlight}; padding:16px 18px 2px; margin:4px 0 20px; }}
.issues {{ list-style:none; padding:0; }}
.issues li {{ padding:14px 0; border-bottom:1px solid var(--rule); margin:0; }}
.issues a {{ font-weight:bold; font-size:18px; }}
.issues span {{ display:block; color:var(--muted); font-size:14px; }}
@media (max-width:620px) {{
  header .logo, header .band, main, footer {{ padding-left:16px; padding-right:16px; }}
  header h1 {{ font-size:24px; }}
  body {{ font-size:16px; }}
}}
@media print {{
  body {{ background:#fff; }}
  .wrap {{ max-width:none; }}
  a {{ color:var(--text); }}
}}
"""


def web_shell(b, page_title, eyebrow, heading, main_html, description=""):
    c = b["colors"]
    css = WEB_CSS.format(font=b["font_stack"], logo_width=b["logo_width"], **c)
    contact = f"<p>{html.escape(b['contact_line'])}</p>" if b.get("contact_line") else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="description" content="{html.escape(description)}">
<title>{html.escape(page_title)}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="logo"><img src="{html.escape(b['logo_url'])}" alt="{html.escape(b['logo_alt'])}"></div>
  <div class="band"><p class="eyebrow">{html.escape(eyebrow)}</p><h1>{html.escape(heading)}</h1></div>
</header>
<main>
{main_html}
</main>
<footer>
  {contact}
  <p>{html.escape(b.get('attribution') or f"{b['district_name']} {b['update_name']}")}</p>
</footer>
</div>
</body>
</html>
"""


def build_web(issue, b, archive_url):
    body = markdown.markdown(issue["body_md"], extensions=["tables", "md_in_html"])
    body = body.replace("<table>", '<div class="table-scroll"><table>').replace("</table>", "</table></div>")
    meta = f'<p class="meta">{long_date(issue["date"])} &middot; <a href="{html.escape(archive_url)}">All updates</a></p>'
    return web_shell(
        b,
        f"{b['district_name']} {b['update_name']}: {issue['week_label']}",
        b["update_name"],
        issue["week_label"],
        meta + "\n" + body,
        issue["preheader"],
    )


def build_archive(b, out_dir):
    entries = []
    for d in sorted((p for p in out_dir.iterdir() if p.is_dir()), reverse=True):
        info = d / "issue.json"
        if info.exists():
            entries.append(json.loads(info.read_text()))
    items = "\n".join(
        f'<li><a href="{e["issue_date"]}/">{html.escape(e["week_label"])}</a>'
        f'<span>{html.escape(e["long_date"])} &middot; {html.escape(e["preheader"])}</span></li>'
        for e in entries
    )
    return web_shell(
        b,
        f"{b['district_name']} {b['update_name']}s",
        b["district_name"],
        f"{b['update_name']}s",
        f'<ul class="issues">\n{items}\n</ul>',
    )


# ---------- driver ----------

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    issue = load_issue(sys.argv[1])
    wanted = sys.argv[2:]
    kits = sorted(BRANDS.glob("*.json"))
    if wanted:
        kits = [k for k in kits if k.stem in wanted]
    if not kits:
        sys.exit("No matching brand kits in brands/.")
    for kit in kits:
        b = json.loads(kit.read_text())
        d_issue = dict(issue)
        changes = []
        ov = load_overrides(issue, b["slug"])
        if ov:
            d_issue["body_md"], d_issue["preheader"], changes = apply_overrides(issue, ov, b)
        base = b["web_base_url"].rstrip("/") + "/"
        web_url = f"{base}{issue['issue_date']}/"
        out_dir = DIST / b["slug"]
        issue_dir = out_dir / issue["issue_date"]
        issue_dir.mkdir(parents=True, exist_ok=True)
        (issue_dir / "index.html").write_text(build_web(d_issue, b, base), encoding="utf-8")
        (issue_dir / "email.html").write_text(build_email(d_issue, b, web_url), encoding="utf-8")
        (issue_dir / "email.txt").write_text(build_text(d_issue, b, web_url), encoding="utf-8")
        report = issue_dir / "changes.txt"
        if changes:
            report.write_text(f"{b['district_name']} differs from the master issue ({ov['file']}):\n"
                              + "\n".join(f"- {c}" for c in changes) + "\n", encoding="utf-8")
        elif report.exists():
            report.unlink()
        (issue_dir / "issue.json").write_text(json.dumps({
            "issue_date": issue["issue_date"],
            "week_label": issue["week_label"],
            "long_date": long_date(issue["date"]),
            "preheader": d_issue["preheader"],
        }, indent=2))
        (out_dir / "index.html").write_text(build_archive(b, out_dir), encoding="utf-8")
        print(f"{b['district_name']}: {issue_dir.relative_to(ROOT)}  ->  {web_url}")
        for c in changes:
            print(f"    customized: {c}")
        if not changes:
            print("    no customizations (master copy as is)")


if __name__ == "__main__":
    main()
