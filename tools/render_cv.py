#!/usr/bin/env python3
"""Job Search Full-Ops Agent: 1-page ATS CV renderer and fact linter.

Takes a CV content file (schemas/cv_content.schema.json, written by Claude in SKILL.md Step 7) and the layout from
config.json, then:
  1. fits the content onto exactly one page: stretches spacing to fill the page, or compresses spacing and (within
     limits) the font size; never cuts content itself, which is Claude's job;
  2. renders a text-based single-column PDF that ATS parsers can read (PDF is the only output format);
  3. lints the result: page overflow, summary length, bullets longer than 2 lines, widow lines, and (with --profile)
     facts: every number, employer, title and certification must come from user_profile.json; guardrail terms are
     blocked;
  4. checks ATS keywords (target_keywords): every keyword the profile supports must appear in the CV in the job's
     exact wording, backed by evidence found in the profile; unsupported keywords must not appear.

Prints a JSON report to stdout. Exit codes: 0 = OK, 1 = errors (CV must be fixed), 2 = usage/config problem.

Usage:
  python tools/render_cv.py runs/cv_<job>.json --config config.json --profile user_profile.json [--out cv.pdf]
                            [--check] [--no-shrink]
  printf '%s\\n' "bullet one" "bullet two" | python tools/render_cv.py --lint-bullets --config config.json
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cv_rules import (achievement_has_metric, check_years_claims, has_result_metric, never_claim_hits,  # noqa: E402
                      unsupported_quantities)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "cv_content.schema.json"
MAX_FONT_GROW_PT = 1.0     # short CVs may grow the body font by up to 1pt to fill the page

# ---------------------------------------------------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------------------------------------------------
MIN_FONT_PT = 9.5          # never shrink body text below this (readability / ATS)
FONT_STEP_PT = 0.25
SPACING_MIN, SPACING_MAX = 0.7, 2.5   # multiplier on the base paragraph spacing
FILL_TARGET = 0.97         # stretch spacing until content fills ~97% of the usable height
UNDERFILL_WARN = 0.90      # warn if the page is emptier than this after stretching
SAFETY = 0.995             # measured height must stay below this share of the usable height
WIDOW_MIN_FILL = 0.30      # the last line of a multi-line bullet must fill >= 30% of the line
LEADING = 1.15

DEFAULT_CV = {
    "page_size": "A4",
    "margins_inch": {"top": 0.5, "bottom": 0.5, "left": 0.5, "right": 0.5},
    "font_family": "Arial",
    "font_size_body_pt": 10,
    "accent_color": "#215E99",
    "section_order": ["summary", "skills", "experience", "education", "certifications", "languages"],
    "summary_max_lines": 4,
    "bullets_most_recent_role": {"min": 3, "max": 4},
    "bullets_older_roles": {"min": 2, "max": 3},
    "max_roles_shown": 4,
    "min_quantified_bullets": 3,
    "show_learning_line": True,
    "max_learning_items": 3,
    "file_name_template": "CV_{full_name}_{company}_{date}",
    "local_output_dir": "output_resumes",
}

SECTION_TITLES = {
    "summary": "Professional Summary", "skills": "Skills", "experience": "Experience", "projects": "Projects",
    "education": "Education", "certifications": "Certifications", "languages": "Languages",
    "volunteering": "Volunteering",
}

# Font families to try, in order: (regular, bold, italic, bold-italic). Liberation Sans is metric-compatible with Arial.
_MAC = "/System/Library/Fonts/Supplemental"
_WIN = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
FONT_SETS = [
    ("Arial", [f"{_MAC}/Arial.ttf", f"{_MAC}/Arial Bold.ttf", f"{_MAC}/Arial Italic.ttf", f"{_MAC}/Arial Bold Italic.ttf"]),
    ("Arial", ["/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf", "/Library/Fonts/Arial Italic.ttf",
               "/Library/Fonts/Arial Bold Italic.ttf"]),
    ("Arial", [os.path.join(_WIN, f) for f in ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf")]),
    ("Liberation Sans", [f"/usr/share/fonts/truetype/liberation/LiberationSans-{s}.ttf"
                         for s in ("Regular", "Bold", "Italic", "BoldItalic")]),
    ("Liberation Sans", [f"/usr/share/fonts/liberation-sans/LiberationSans-{s}.ttf"
                         for s in ("Regular", "Bold", "Italic", "BoldItalic")]),
    ("DejaVu Sans", [f"/usr/share/fonts/truetype/dejavu/DejaVuSans{s}.ttf"
                     for s in ("", "-Bold", "-Oblique", "-BoldOblique")]),
]
BUILTIN = ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique")


class UsageError(Exception):
    pass


# ---------------------------------------------------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------------------------------------------------
def load_fonts(cv: dict, sample_text: str) -> tuple[tuple[str, str, str, str], str]:
    """Register a Unicode TTF family and return (font names, label). European names (ł, ő, ş, ø…) need a real TTF."""
    files = cv.get("font_files")
    candidates = []
    if files:
        candidates.append(("custom", [files.get(k) for k in ("regular", "bold", "italic", "bold_italic")]))
    wanted = (cv.get("font_family") or "").lower()
    # Try the requested family first, then everything else.
    candidates += sorted(FONT_SETS, key=lambda fs: 0 if fs[0].lower() == wanted else 1)
    for label, paths in candidates:
        if paths and all(p and os.path.exists(p) for p in paths):
            names = tuple(f"EJ-{label.replace(' ', '')}-{i}" for i in range(4))
            for n, p in zip(names, paths):
                if n not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(n, p))
            pdfmetrics.registerFontFamily(names[0], normal=names[0], bold=names[1], italic=names[2],
                                          boldItalic=names[3])
            return names, label
    if files:
        raise UsageError(f"cv.font_files set but not all four files exist: {files}")
    try:
        sample_text.encode("cp1252")
    except UnicodeEncodeError:
        raise UsageError("No Unicode TTF font found (Arial / Liberation Sans / DejaVu Sans) and the CV contains "
                         "characters outside Latin-1. Install one of them or set cv.font_files in config.json.")
    return BUILTIN, "Helvetica (built-in)"


# ---------------------------------------------------------------------------------------------------------------------
# Story
# ---------------------------------------------------------------------------------------------------------------------
def _e(text) -> str:
    return escape(str(text or "").strip())


def build_story(content: dict, cv: dict, fonts, size: float, s: float):
    """Return (flowables, tracked) where tracked = [(kind, key, paragraph)] for line analysis."""
    reg, bold, ital, boldital = fonts
    accent_hex = cv["accent_color"]
    accent = HexColor(accent_hex)
    sep = f' <font color="{accent_hex}">\u2022</font> '

    def st(name, **kw):
        base = dict(fontName=reg, fontSize=size, leading=size * LEADING, textColor=black)
        base.update(kw)
        return ParagraphStyle(name, **base)

    small = size - 0.5
    S = {
        "name": st("name", fontName=bold, fontSize=size * 1.8, leading=size * 2.1, textColor=accent),
        "headline": st("headline", spaceBefore=1 * s),
        "contact": st("contact", fontSize=small, leading=small * LEADING, spaceBefore=1 * s),
        "h": st("h", fontName=bold, fontSize=size + 2, leading=(size + 2) * 1.2, textColor=accent,
                spaceBefore=6 * s, spaceAfter=2 * s),
        "body": st("body"),
        "title": st("title", fontName=bold, fontSize=size + 0.5, leading=(size + 0.5) * LEADING, spaceBefore=4 * s),
        "company": st("company", fontName=boldital, fontSize=small, leading=small * LEADING, textColor=accent,
                      spaceAfter=1 * s),
        "tagline": st("tagline", fontName=ital, spaceAfter=1 * s),
        "bullet": st("bullet", leftIndent=11, bulletIndent=2, bulletFontName=reg, bulletFontSize=size,
                     bulletColor=accent, spaceAfter=1 * s),
        "line": st("line", spaceAfter=1 * s),
    }
    story, tracked = [], []

    def add(p, kind=None, key=None):
        story.append(p)
        if kind:
            tracked.append((kind, key, p))

    hdr = content["header"]
    add(Paragraph(_e(hdr["name"]), S["name"]))
    if hdr.get("headline"):
        add(Paragraph(_e(hdr["headline"]), S["headline"]))
    parts = []
    for c in hdr.get("contact", []):
        t = _e(c["text"])
        parts.append(f'<link href="{escape(c["url"])}"><u>{t}</u></link>' if c.get("url") else t)
    if parts:
        add(Paragraph(sep.join(parts), S["contact"]))

    learning = content.get("learning") if cv.get("show_learning_line", True) else None
    for sec in cv["section_order"]:
        data = content.get(sec)
        if not data:
            continue
        if sec == "skills" and not (content.get("skills") or content.get("tools") or learning):
            continue
        add(Paragraph(SECTION_TITLES[sec], S["h"]))
        if sec == "summary":
            add(Paragraph(_e(data), S["body"]), "summary", "summary")
        elif sec == "skills":
            if content.get("skills"):
                add(Paragraph(sep.join(_e(x) for x in content["skills"]), S["line"]), "skills", "skills")
            if content.get("tools"):
                add(Paragraph("<b>Tools:</b> " + sep.join(_e(x) for x in content["tools"]), S["line"]),
                    "skills", "tools")
            if learning:
                add(Paragraph("<b>Learning:</b> " + sep.join(_e(x) for x in learning), S["line"]),
                    "skills", "learning")
        elif sec == "experience":
            for i, role in enumerate(data):
                add(Paragraph(_e(role["title"]), S["title"]))
                meta = " | ".join(_e(x) for x in (role.get("company"), role.get("location"), role.get("dates")) if x)
                add(Paragraph(meta, S["company"]))
                if role.get("tagline"):
                    add(Paragraph(_e(role["tagline"]), S["tagline"]))
                for j, b in enumerate(role["bullets"]):
                    add(Paragraph(_e(b), S["bullet"], bulletText="\u2022"), "bullet", f"experience[{i}].bullets[{j}]")
        elif sec == "projects":
            for i, p in enumerate(data):
                add(Paragraph(f"<b>{_e(p['name'])}</b> \u2013 {_e(p['line'])}", S["bullet"], bulletText="\u2022"),
                    "bullet", f"projects[{i}]")
        elif sec == "education":
            for ed in data:
                tail = " | ".join(_e(x) for x in (ed.get("dates"), ed.get("institution")) if x)
                add(Paragraph(f"<b>{_e(ed['degree'])}</b>" + (f" \u2013 {tail}" if tail else ""), S["line"]))
        elif sec == "certifications":
            for c in data:
                txt = _e(c["name"]) + (f" | {_e(c['issuer'])}" if c.get("issuer") else "")
                add(Paragraph(txt, S["bullet"], bulletText="\u2022"))
        elif sec == "languages":
            add(Paragraph(sep.join(f"{_e(l['language'])} ({_e(l['level'])})" for l in data), S["line"]))
        elif sec == "volunteering":
            for i, v in enumerate(data):
                add(Paragraph(_e(v), S["bullet"], bulletText="\u2022"), "bullet", f"volunteering[{i}]")
    return story, tracked


def measure(story, width: float) -> float:
    """Total height the story needs in a zero-padding frame (spaceBefore collapses with the previous spaceAfter,
    as in reportlab's Frame)."""
    total, prev_after = 0.0, 0.0
    for i, f in enumerate(story):
        _, h = f.wrap(width, 1e6)
        before = 0.0 if i == 0 else max(f.getSpaceBefore() - prev_after, 0.0)
        prev_after = f.getSpaceAfter()
        total += before + h + prev_after
    return total


# ---------------------------------------------------------------------------------------------------------------------
# Fitting & rendering
# ---------------------------------------------------------------------------------------------------------------------
def page_geometry(cv: dict):
    page = A4 if cv["page_size"] == "A4" else LETTER
    m = cv["margins_inch"]
    width = page[0] - (m["left"] + m["right"]) * inch
    height = page[1] - (m["top"] + m["bottom"]) * inch
    return page, width, height


def fit(content, cv, fonts, allow_shrink=True):
    """Choose (font size, spacing multiplier). Returns dict with fits flag and the measured height."""
    _, width, height = page_geometry(cv)
    base = float(cv["font_size_body_pt"])
    sizes = [base]
    if allow_shrink:
        x = base - FONT_STEP_PT
        while x >= MIN_FONT_PT - 1e-9:
            sizes.append(round(x, 2))
            x -= FONT_STEP_PT

    def h(sz, s):
        return measure(build_story(content, cv, fonts, sz, s)[0], width)

    chosen = None
    for sz in sizes:
        if h(sz, SPACING_MIN) <= SAFETY * height:
            chosen = sz
            break
    if chosen is None:
        sz = sizes[-1]
        need = h(sz, SPACING_MIN)
        return {"fits": False, "font_size": sz, "spacing": SPACING_MIN, "height": need, "usable": height}

    if allow_shrink and chosen == base and h(base, SPACING_MAX) < UNDERFILL_WARN * height:
        # Short CV: a slightly larger font reads better than huge gaps. Grow in steps while it still fits at
        # normal spacing.
        x = base + FONT_STEP_PT
        while x <= base + MAX_FONT_GROW_PT + 1e-9 and h(round(x, 2), 1.0) <= FILL_TARGET * height:
            chosen = round(x, 2)
            x += FONT_STEP_PT

    limit = (FILL_TARGET if h(chosen, 1.0) <= FILL_TARGET * height else SAFETY) * height
    lo, hi = SPACING_MIN, SPACING_MAX
    for _ in range(18):
        mid = (lo + hi) / 2
        if h(chosen, mid) <= limit:
            lo = mid
        else:
            hi = mid
    return {"fits": True, "font_size": chosen, "spacing": round(lo, 3), "height": h(chosen, lo), "usable": height}


def render_pdf(content, cv, fonts, size, s, target) -> int:
    """Build the PDF into `target` (path or BytesIO). Returns the number of pages produced."""
    page, width, height = page_geometry(cv)
    m = cv["margins_inch"]
    pages = {"n": 0}

    def on_page(canvas, doc):
        pages["n"] += 1

    frame = Frame(m["left"] * inch, m["bottom"] * inch, width, height, id="body",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0)
    doc = BaseDocTemplate(target, pagesize=page, leftMargin=m["left"] * inch, rightMargin=m["right"] * inch,
                          topMargin=m["top"] * inch, bottomMargin=m["bottom"] * inch,
                          title=f"CV - {content['header']['name']}", author=content["header"]["name"],
                          subject=content.get("company") or "", creator="Job Search Full-Ops Agent")
    doc.addPageTemplates([PageTemplate(id="cv", frames=[frame], onPage=on_page)])
    doc.build(build_story(content, cv, fonts, size, s)[0])
    return pages["n"]


# ---------------------------------------------------------------------------------------------------------------------
# Line analysis
# ---------------------------------------------------------------------------------------------------------------------
def line_stats(p: Paragraph) -> tuple[int, float]:
    """(number of lines, fill ratio of the last line) for a paragraph that has been wrapped."""
    lines = p.blPara.lines
    if not lines:
        return 0, 0.0
    usable = p.width - p.style.leftIndent - p.style.rightIndent
    last = lines[-1]
    extra = last.extraSpace if hasattr(last, "extraSpace") else last[0]
    return len(lines), max(0.0, min(1.0, (usable - extra) / usable)) if usable > 0 else 0.0


def analyse_lines(content, cv, fonts, size, s, max_summary_lines):
    _, width, _ = page_geometry(cv)
    story, tracked = build_story(content, cv, fonts, size, s)
    measure(story, width)
    errors, warnings, details = [], [], []
    for kind, key, p in tracked:
        n, fill = line_stats(p)
        if kind == "summary":
            details.append({"key": key, "lines": n})
            if n > max_summary_lines:
                errors.append(f"summary has {n} lines (max {max_summary_lines}): shorten it")
        elif kind == "bullet":
            details.append({"key": key, "lines": n, "last_line_fill": round(fill, 2)})
            if n > 2:
                warnings.append(f"{key}: {n} lines (max 2): shorten")
            elif n == 2 and fill < WIDOW_MIN_FILL:
                warnings.append(f"{key}: widow line ({fill:.0%} of width): shorten to 1 line or lengthen")
    return errors, warnings, details


# ---------------------------------------------------------------------------------------------------------------------
# Fact & rule lint
# ---------------------------------------------------------------------------------------------------------------------
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")


def norm_number(raw) -> str:
    raw = str(raw).strip()
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw) or re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        raw = re.sub(r"[.,]", "", raw)          # thousands separators: 4,000 / 4.000
    raw = raw.replace(",", ".")                 # decimal comma: 1,5
    try:
        v = float(raw)
    except ValueError:
        return raw
    return str(int(v)) if v.is_integer() else repr(v)


def numbers_in(obj) -> set[str]:
    out = set()
    if isinstance(obj, dict):
        for v in obj.values():
            out |= numbers_in(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= numbers_in(v)
    elif isinstance(obj, bool) or obj is None:
        pass
    elif isinstance(obj, (int, float)):
        out.add(norm_number(str(obj)))
    elif isinstance(obj, str):
        out |= {norm_number(n) for n in NUM_RE.findall(obj)}
    return out


def visible_text(content: dict) -> str:
    """Everything printed on the CV, without urls, the target company and the derived-number notes."""
    c = {k: v for k, v in content.items() if k not in ("$schema", "job_id", "company", "derived_numbers")}
    c["header"] = {**content["header"], "contact": [x["text"] for x in content["header"].get("contact", [])]}
    parts = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            parts.append(o)
    walk(c)
    return "\n".join(parts)


def claims_text(content: dict) -> str:
    """CV text that makes claims: everything printed except contact details and employment / study dates."""
    parts = [content["header"].get("headline", ""), content.get("summary", "")]
    parts += content.get("skills", []) + content.get("tools", []) + content.get("learning", [])
    for r in content.get("experience", []):
        parts += [r.get("title", ""), r.get("company", ""), r.get("location", ""), r.get("tagline", "")] + r["bullets"]
    for p in content.get("projects", []):
        parts += [p.get("name", ""), p.get("line", "")]
    for e in content.get("education", []):
        parts += [e.get("degree", ""), e.get("institution", "")]
    for c in content.get("certifications", []):
        parts += [c.get("name", ""), c.get("issuer") or ""]
    parts += content.get("volunteering", [])
    return "\n".join(p for p in parts if p)


def _n(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def lint_facts(content: dict, profile: dict, cv: dict):
    errors, warnings, info = [], [], {}
    text = visible_text(content)
    low = text.lower()

    # 1. every figure must exist in the profile with the same kind and value: a percentage as a percentage, a
    # multiple as a multiple, money with its amount and currency. Numbers written as words are checked too.
    # Dates and phone digits in the profile don't count as evidence.
    unsupported = unsupported_quantities(claims_text(content), profile, content.get("derived_numbers", []))
    if unsupported:
        shown = ", ".join(f"'{q['text']}' ({q['kind']})" for q in unsupported)
        errors.append(f"numbers not found in user_profile.json: {shown}. Use the exact figure from the profile, or, "
                      f"if it's calculated from profile facts, declare it in derived_numbers with a basis")
    if content.get("derived_numbers"):
        info["derived_numbers_to_review"] = content.get("derived_numbers", [])

    # 2. guardrails
    roles = profile.get("experience", [])
    never = list(profile.get("guardrails", {}).get("never_claim", []))
    for r in roles:
        never += r.get("never_claim", [])
    for phrase, matched in never_claim_hits(text, never):
        errors.append(f"guardrail: never claim '{phrase}', but the CV says '{matched}'. Rewrite it so it doesn't "
                      f"read as that claim")
    for term in profile.get("guardrails", {}).get("excluded_terms", []):
        if term and re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", low):
            errors.append(f"guardrail: CV contains excluded term '{term}'")
    if re.search(r"\bbudget", low) and not any(r.get("scope", {}).get("budget_owned") for r in roles):
        errors.append("guardrail: CV mentions a budget but no role in the profile has scope.budget_owned")

    # 2b. "N years" must match the role dates
    head_text = f"{content['header'].get('headline', '')}\n{content.get('summary', '')}"
    for problem in check_years_claims(head_text, roles, content.get("derived_numbers", [])):
        errors.append(f"years of experience: {problem}")

    # 3. employers and titles must match the profile exactly
    by_id = {r.get("id"): r for r in roles}
    for i, role in enumerate(content.get("experience", [])):
        src = by_id.get(role.get("role_id")) or next(
            (r for r in roles if _n(r.get("company")) == _n(role.get("company"))), None)
        if not src:
            errors.append(f"experience[{i}]: company '{role.get('company')}' is not in the profile")
            continue
        if _n(src.get("company")) != _n(role.get("company")):
            errors.append(f"experience[{i}]: company '{role.get('company')}' differs from profile "
                          f"'{src.get('company')}'")
        if _n(src.get("title")) != _n(role.get("title")):
            errors.append(f"experience[{i}]: title '{role.get('title')}' differs from profile '{src.get('title')}'")

    # 4. certifications must be in the profile and allowed on the CV
    certs = {_n(c.get("name")): c for c in profile.get("certifications", [])}
    for c in content.get("certifications", []):
        src = certs.get(_n(c.get("name")))
        if not src:
            errors.append(f"certification '{c.get('name')}' is not in the profile")
        elif src.get("show_on_cv") is False:
            errors.append(f"certification '{c.get('name')}' has show_on_cv: false")

    # 5. measured-result bullets: same rule as the onboarding quality gate (tools/cv_rules.py). The target is
    # cv.min_quantified_bullets, but never more than the profile can supply for the roles shown on the CV.
    exp = content.get("experience", [])
    quantified = sum(1 for r in exp for b in r["bullets"] if has_result_metric(b))
    shown = {(r.get("role_id") or "").strip() for r in exp}
    available = sum(1 for r in roles if r.get("id") in shown for a in r.get("achievements", [])
                    if a.get("allowed_in_cv", True) and achievement_has_metric(a))
    target = int(cv.get("min_quantified_bullets", 0))
    need = min(target, available)
    info["quantified_bullets"] = quantified
    info["metric_bullets_available_in_profile"] = available
    if quantified < need:
        errors.append(f"only {quantified} bullet{'' if quantified == 1 else 's'} with a measured result, but the "
                      f"profile has {available} for these roles (target {target}): use them")
    elif need < target:
        info["metric_note"] = (f"the profile has only {available} measured results for these roles, so {need} is "
                               f"enough (target {target})")
    for i, r in enumerate(exp):
        rng = cv["bullets_most_recent_role"] if i == 0 else cv["bullets_older_roles"]
        n = len(r["bullets"])
        if not rng["min"] <= n <= rng["max"]:
            warnings.append(f"experience[{i}]: {n} bullets (expected {rng['min']}-{rng['max']})")
    if len(exp) > cv.get("max_roles_shown", 99):
        warnings.append(f"{len(exp)} roles shown (max_roles_shown {cv['max_roles_shown']})")
    return errors, warnings, info


# ---------------------------------------------------------------------------------------------------------------------
# ATS keyword lint
# ---------------------------------------------------------------------------------------------------------------------
KEYWORD_MAX_REPEATS = 3


def _kw_pattern(keyword: str) -> re.Pattern:
    """Whole-phrase, case-insensitive match; whitespace and hyphen/space variants are treated as equal."""
    parts = [re.escape(p) for p in re.split(r"[\s\-]+", keyword.strip()) if p]
    return re.compile(r"(?<![\w-])" + r"[\s\-]+".join(parts) + r"(?![\w-])", re.IGNORECASE)


def section_texts(content: dict) -> dict:
    exp = content.get("experience", [])
    return {
        "headline": content["header"].get("headline", ""),
        "summary": content.get("summary", ""),
        "skills": " | ".join(content.get("skills", [])),
        "tools": " | ".join(content.get("tools", [])),
        "learning": " | ".join(content.get("learning", [])),
        "experience": "\n".join([r.get("title", "") for r in exp] + [r.get("tagline", "") for r in exp]
                                + [b for r in exp for b in r["bullets"]]
                                + [p.get("name", "") + " " + p.get("line", "") for p in content.get("projects", [])]),
    }


def lint_keywords(content: dict, profile: dict | None):
    """Every supported job keyword must be in the CV, in the job's wording; unsupported ones must not be."""
    errors, warnings = [], []
    kws = content.get("target_keywords")
    if not kws:
        warnings.append("no target_keywords: ATS keyword coverage was not checked")
        return errors, warnings, {}
    sections = section_texts(content)
    claimed = "\n".join(v for k, v in sections.items() if k != "learning")   # text that presents experience
    learning_names = {_n(x.get("name")) for x in (profile or {}).get("skills", {}).get("learning", [])}
    body = sections["headline"] + "\n" + sections["summary"] + "\n" + sections["experience"]
    full = "\n".join(sections.values())
    profile_text = _n(visible_text({"header": {"name": ""}, **profile})) if profile else None
    tally = {"must": [0, 0], "nice": [0, 0]}
    absent_from_profile, learning_kws = [], []
    for k in kws:
        kw, status, prio = k["keyword"], k["status"], k.get("priority", "nice")
        pat = _kw_pattern(kw)
        hits = len(pat.findall(full))
        if status == "missing":
            absent_from_profile.append(kw)
            if hits:
                errors.append(f"keyword '{kw}' is marked missing (not supported by the profile) but appears on the "
                              f"CV: remove it, or mark it matched with evidence if the profile does support it")
            continue
        if status == "learning":
            learning_kws.append(kw)
            if profile is not None and _n(k.get("evidence") or kw) not in learning_names:
                errors.append(f"keyword '{kw}' is marked learning but is not in the profile's skills.learning")
            if _kw_pattern(kw).search(claimed):
                errors.append(f"keyword '{kw}' is only being learned but appears outside the Learning line, which "
                              f"presents it as experience: move it to the Learning line")
            elif not pat.search(sections["learning"]):
                warnings.append(f"learning keyword '{kw}' is not on the Learning line")
            continue
        tally[prio][1] += 1
        if not k.get("evidence"):
            errors.append(f"keyword '{kw}' is marked {status} but has no evidence from the profile")
        elif profile_text is not None and _n(k["evidence"]) not in profile_text:
            errors.append(f"keyword '{kw}': evidence '{k['evidence']}' was not found in user_profile.json")
        if not hits:
            (errors if prio == "must" else warnings).append(
                f"{prio} keyword '{kw}' ({status}) is not on the CV: work it into the summary, skills or a bullet "
                f"in the job's exact wording")
            continue
        tally[prio][0] += 1
        if prio == "must" and not pat.search(body):
            warnings.append(f"must keyword '{kw}' appears only in the skills/tools lines: also use it in the "
                            f"summary or a bullet where the profile supports it")
        if hits > KEYWORD_MAX_REPEATS:
            warnings.append(f"keyword '{kw}' appears {hits} times: more than {KEYWORD_MAX_REPEATS} reads as "
                            f"keyword stuffing")
        for sec in k.get("placed_in", []):
            if not pat.search(sections.get(sec, "")):
                warnings.append(f"keyword '{kw}' listed as placed in {sec} but not found there")
    info = {"keyword_coverage": {
        "must": f"{tally['must'][0]}/{tally['must'][1]}",
        "nice": f"{tally['nice'][0]}/{tally['nice'][1]}",
        "on_learning_line": learning_kws,
        "not_supported_by_profile": absent_from_profile,
    }}
    return errors, warnings, info


def lint_learning(content: dict, profile: dict | None, cv: dict):
    """The Learning line may only hold skills the user confirmed they are learning (profile skills.learning)."""
    errors, warnings = [], []
    items = content.get("learning") or []
    if not items:
        return errors, warnings
    if not cv.get("show_learning_line", True):
        warnings.append("content has a learning list but cv.show_learning_line is false: it was not rendered")
        return errors, warnings
    limit = int(cv.get("max_learning_items", 3))
    if len(items) > limit:
        errors.append(f"Learning line has {len(items)} items (max_learning_items {limit}): keep the most relevant")
    if profile is None:
        return errors, warnings
    skills = profile.get("skills", {})
    allowed = {_n(x.get("name")) for x in skills.get("learning", [])}
    used = {_n(x) for k in ("core", "tools", "methodologies", "technical") for x in skills.get(k, [])}
    for item in items:
        if _n(item) not in allowed:
            errors.append(f"Learning line item '{item}' is not in the profile's skills.learning: ask the user first")
        elif _n(item) in used:
            warnings.append(f"'{item}' is both a used skill and a learning item in the profile: list it under Skills")
    return errors, warnings


# ---------------------------------------------------------------------------------------------------------------------
# Paths & CLI
# ---------------------------------------------------------------------------------------------------------------------
def _slug(s: str) -> str:
    return re.sub(r"[^\w\-]+", "_", s, flags=re.UNICODE).strip("_") or "Company"


def default_out(content: dict, cv: dict, root: Path) -> Path:
    """<local_output_dir>/<Company>_<YYYY-MM-DD>[_N]/<file name>.pdf; never reuses an existing folder."""
    today = date.today().isoformat()
    company = _slug(content.get("company") or "Company")
    base = root / cv["local_output_dir"] / f"{company}_{today}"
    folder, k = base, 2
    while folder.exists():
        folder = base.with_name(f"{base.name}_{k}")
        k += 1
    name = cv["file_name_template"].format(full_name=_slug(content["header"]["name"]), company=company, date=today)
    return folder / f"{name.replace('/', '_')}.pdf"


def load_cv_config(path: str | None) -> dict:
    cv = dict(DEFAULT_CV)
    if path:
        try:
            cfg = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise UsageError(f"cannot read config {path}: {e}")
        cv.update(cfg.get("cv", {}))
    if cv.get("max_pages", 1) != 1:
        raise UsageError("cv.max_pages must be 1")
    return cv


def unused_profile_bullets(content: dict, profile: dict) -> int:
    """How many allowed achievements of the roles shown on the CV are not on it yet."""
    by_id = {r.get("id"): r for r in profile.get("experience", [])}
    unused = 0
    for role in content.get("experience", []):
        src = by_id.get(role.get("role_id"))
        if src:
            allowed = sum(1 for a in src.get("achievements", []) if a.get("allowed_in_cv", True))
            unused += max(0, allowed - len(role.get("bullets", [])))
    return unused


def validate_content(content: dict) -> None:
    """Check the CV content against schemas/cv_content.schema.json before doing anything else, so bad input gives a
    clear exit-2 message instead of a crash."""
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        Draft202012Validator = None
    if Draft202012Validator and SCHEMA_PATH.exists():
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        errs = sorted(Draft202012Validator(schema).iter_errors(content), key=lambda e: list(e.path))
        if errs:
            lines = [f"{'/'.join(str(p) for p in e.path) or '(top level)'}: {e.message}" for e in errs[:8]]
            more = f" (+{len(errs) - 8} more)" if len(errs) > 8 else ""
            raise UsageError("CV content does not match schemas/cv_content.schema.json" + more + ": "
                             + "; ".join(lines))
    else:
        for key in ("header", "summary", "experience"):
            if key not in content:
                raise UsageError(f"content is missing '{key}' (see schemas/cv_content.schema.json)")


def run(args) -> tuple[dict, int]:
    cv = load_cv_config(args.config)

    if args.lint_bullets:
        lines = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
        content = {"header": {"name": "x"}, "summary": "", "experience": [{"title": "", "company": "", "dates": "",
                                                                            "bullets": lines or ["x"]}]}
        fonts, _ = load_fonts(cv, "\n".join(lines))
        _, warnings, details = analyse_lines(content, cv, fonts, float(cv["font_size_body_pt"]), 1.0, 99)
        for d, text in zip(details, lines):
            d["text"] = text
        return {"bullets": details, "warnings": warnings}, 0

    if not args.content:
        raise UsageError("CONTENT file is required (or use --lint-bullets)")
    try:
        content = json.loads(Path(args.content).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise UsageError(f"cannot read content {args.content}: {e}")
    validate_content(content)

    fonts, font_label = load_fonts(cv, visible_text(content))
    errors, warnings = [], []
    report = {"content": args.content, "font": font_label}

    f = fit(content, cv, fonts, allow_shrink=not args.no_shrink)
    size, s = f["font_size"], f["spacing"]

    pages, out_path = None, None
    if f["fits"]:
        for _ in range(12):        # verify with a real build; nudge spacing down if reportlab disagrees
            buf = io.BytesIO()
            pages = render_pdf(content, cv, fonts, size, s, buf)
            if pages == 1 or s <= SPACING_MIN:
                break
            s = max(SPACING_MIN, round(s * 0.96, 3))
        if pages != 1:
            f["fits"] = False
    if not f["fits"]:
        over = f["height"] - f["usable"] * SAFETY if pages is None else None
        msg = "CV does not fit on one page"
        if over and over > 0:
            msg += f": about {over:.0f}pt (~{over / (size * LEADING):.0f} lines) too long at {size}pt with minimum " \
                   f"spacing. Cut content in this order: weakest bullet without a metric, a bullet from the oldest " \
                   f"role, one summary line, the oldest role"
        errors.append(msg)

    line_err, line_warn, details = analyse_lines(content, cv, fonts, size, s, int(cv["summary_max_lines"]))
    errors += line_err
    warnings += line_warn

    profile = None
    if args.profile:
        try:
            profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise UsageError(f"cannot read profile {args.profile}: {e}")
        fe, fw, info = lint_facts(content, profile, cv)
        errors += fe
        warnings += fw
        report.update(info)
    else:
        warnings.append("no --profile given: fact checks (numbers, employers, titles, guardrails, keyword "
                        "evidence) were skipped")
    ke, kw_warn, kinfo = lint_keywords(content, profile)
    errors += ke
    warnings += kw_warn
    report.update(kinfo)
    le, lw = lint_learning(content, profile, cv)
    errors += le
    warnings += lw

    fill = f["height"] / f["usable"] if f["fits"] else None
    if fill is not None and fill < UNDERFILL_WARN:
        unused = unused_profile_bullets(content, profile) if profile else None
        if unused == 0:
            report["short_cv"] = (f"page {fill:.0%} full and every profile bullet for these roles is already used; "
                                  f"a shorter CV is fine")
        else:
            extra = f" ({unused} unused in the profile)" if unused else ""
            warnings.append(f"page only {fill:.0%} full even with maximum spacing: add a true bullet from the "
                            f"profile{extra}")

    if not errors and not args.check:
        out_path = Path(args.out) if args.out else default_out(content, cv, Path(args.root))
        if out_path.exists():
            raise UsageError(f"{out_path} already exists; refusing to overwrite")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        render_pdf(content, cv, fonts, size, s, str(out_path))
        report["pdf"] = str(out_path.resolve())

    report.update({
        "ok": not errors,
        "pages": pages,
        "fits_one_page": bool(f["fits"]),
        "fill_ratio": round(fill, 3) if fill is not None else None,
        "font_size_pt": size,
        "spacing": s,
        "errors": errors,
        "warnings": warnings,
        "lines": details,
    })
    return report, (0 if not errors else 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render and lint a 1-page ATS CV.")
    ap.add_argument("content", nargs="?", help="CV content JSON (schemas/cv_content.schema.json)")
    ap.add_argument("--config", default="config.json", help="config.json (layout comes from its 'cv' block)")
    ap.add_argument("--profile", help="user_profile.json, enables fact checks (recommended)")
    ap.add_argument("--out", help="output PDF path (default: <local_output_dir>/<Company>_<date>/<name>.pdf)")
    ap.add_argument("--root", default=".", help="repository root for the default output path")
    ap.add_argument("--check", action="store_true", help="fit and lint only; write no files")
    ap.add_argument("--no-shrink", action="store_true", help="never reduce the font size to fit")
    ap.add_argument("--lint-bullets", action="store_true", help="read bullets from stdin, report line counts")
    args = ap.parse_args(argv)
    if args.config == "config.json" and not Path(args.config).exists():
        args.config = None    # fall back to defaults when run outside a configured repo
    try:
        report, code = run(args)
    except UsageError as e:
        print(json.dumps({"ok": False, "usage_error": str(e)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
