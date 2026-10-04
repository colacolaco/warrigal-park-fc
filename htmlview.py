"""Shared HTML building blocks.

The application deliberately has no third-party dependency, so the small amount
of HTML generation it needs lives here rather than in a template language.
Every piece of user-supplied text passes through :func:`esc` before it reaches
the page, which is what prevents a player's name from being interpreted as
markup.
"""

from __future__ import annotations

from html import escape
from typing import Iterable, Mapping, Sequence

from theme import STATUS_COLOURS, STATUS_LABELS, THEME

NAV_ITEMS = (
    ("/", "Dashboard"),
    ("/members", "Members"),
    ("/guardians", "Guardians"),
    ("/registrations", "Registrations"),
    ("/teams", "Teams & Rosters"),
    ("/views", "Views"),
)


def esc(value: object) -> str:
    """Escape text for safe inclusion in HTML."""
    if value is None:
        return ""
    return escape(str(value), quote=True)


def layout(
    title: str,
    body: str,
    active: str = "/",
    notice: tuple[str, str] | None = None,
    environment: str = "development",
) -> str:
    """Wrap page content in the club's standard chrome.

    :param notice: an optional ``(kind, message)`` pair where kind is one of
        ``ok``, ``warn`` or ``error``.
    """
    nav_parts = []
    for href, label in NAV_ITEMS:
        klass = ' class="active"' if href == active else ""
        nav_parts.append(f'<a href="{esc(href)}"{klass}>{esc(label)}</a>')
    nav = "".join(nav_parts)
    notice_html = ""
    if notice:
        kind, message = notice
        notice_html = f'<div class="notice {esc(kind)}">{esc(message)}</div>'

    return f"""<!DOCTYPE html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} &middot; {esc(THEME['club_name'])}</title>
<link rel="stylesheet" href="/static/styles.css">
</head>
<body>
<header class="club-header">
  <div class="inner">
    <div class="crest">WPFC</div>
    <div>
      <h1>{esc(THEME['club_name'])} — {esc(THEME['system_name'])}</h1>
      <p class="sub">Season {esc(THEME['season'])} &middot; replacing the 43-column Excel master spreadsheet</p>
    </div>
    <span class="env-badge">env: {esc(environment)}</span>
  </div>
</header>
<nav class="main-nav"><div class="inner">{nav}</div></nav>
<main>
{notice_html}
{body}
</main>
<footer class="club-footer">
  Warrigal Park FC Member Registration &amp; Team Roster System &middot;
  ISYS3001 Assessment 2 &middot; all sample data is fictitious
</footer>
</body>
</html>
"""


def page_title(text: str, count: str = "") -> str:
    suffix = f'<span class="count">{esc(count)}</span>' if count else ""
    return f'<h1 class="page-title">{esc(text)}{suffix}</h1>'


def help_text(text: str) -> str:
    return f'<p class="page-help">{esc(text)}</p>'


def card(title: str, content: str, subtitle: str = "") -> str:
    sub = f'<p class="page-help">{esc(subtitle)}</p>' if subtitle else ""
    return f'<section class="card"><h2>{esc(title)}</h2>{sub}{content}</section>'


def rule_callout(text: str) -> str:
    return f'<div class="rule">{text}</div>'


def status_badge(status: str) -> str:
    label = STATUS_LABELS.get(status, status)
    colour = STATUS_COLOURS.get(status, THEME["text_muted"])
    return f'<span class="badge" style="background:{esc(colour)}">{esc(label)}</span>'


def badge(text: str, colour: str) -> str:
    return f'<span class="badge" style="background:{esc(colour)}">{esc(text)}</span>'


def table(headers: Sequence[str], rows: Iterable[Sequence[str]], caption: str = "") -> str:
    """Render a data table.  Cell content is inserted verbatim, so callers must
    escape anything that came from a user."""
    cap = f"<caption>{esc(caption)}</caption>" if caption else ""
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{cell}</td>" for cell in row)
        body_rows.append(f"<tr>{cells}</tr>")
    if not body_rows:
        body = (
            f'<tr><td colspan="{len(headers)}">'
            '<span style="color:#6E675E">No records to display.</span></td></tr>'
        )
        body_rows.append(body)
    return (
        f'<table class="data">{cap}<thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


def empty_state(message: str) -> str:
    return f'<div class="empty">{esc(message)}</div>'


def field(
    name: str,
    label: str,
    value: object = "",
    input_type: str = "text",
    required: bool = False,
    hint: str = "",
    options: Mapping[str, str] | Sequence[tuple[str, str]] | None = None,
) -> str:
    """Render one labelled form control."""
    req = " required" if required else ""
    hint_html = f'<span class="hint">{esc(hint)}</span>' if hint else ""
    if options is not None:
        pairs = options.items() if isinstance(options, Mapping) else options
        opts = "".join(
            f'<option value="{esc(key)}"'
            f'{" selected" if str(key) == str(value) else ""}>{esc(text)}</option>'
            for key, text in pairs
        )
        control = f'<select name="{esc(name)}"{req}>{opts}</select>'
    else:
        control = (
            f'<input type="{esc(input_type)}" name="{esc(name)}" '
            f'value="{esc(value)}"{req}>'
        )
    return (
        f'<div class="field"><label for="{esc(name)}">{esc(label)}</label>'
        f"{hint_html}{control}</div>"
    )


def hidden(name: str, value: object) -> str:
    return f'<input type="hidden" name="{esc(name)}" value="{esc(value)}">'


def link(href: str, text: str, css: str = "") -> str:
    klass = f' class="{esc(css)}"' if css else ""
    return f'<a href="{esc(href)}"{klass}>{esc(text)}</a>'
