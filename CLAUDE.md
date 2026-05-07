# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the development server (port 5001)
python app.py

# Run tests
pytest

# Run a single test file
pytest tests/test_app.py

# Run a specific test
pytest tests/test_app.py::test_name
```

## Architecture

**Spendly** is a Flask expense tracker. The stack is Python/Flask + SQLite + Jinja2 templates + vanilla JS, no build step required.

### Entry point

`app.py` — registers all routes and runs on port 5001. Routes are thin: they call database helpers from `database/db.py` and render templates from `templates/`.

### Database layer

`database/db.py` — SQLite via Python's `sqlite3`. Expected helpers: `get_db()`, `init_db()`, `seed_db()`. The schema is not yet implemented; this is the first place to extend. Foreign keys must be enabled explicitly (`PRAGMA foreign_keys = ON`).

### Templates

All templates extend `templates/base.html`, which provides the navbar and footer. The Jinja2 block structure is:
- `{% block title %}` — page `<title>`
- `{% block content %}` — main page body

### Static assets

`static/css/style.css` — single stylesheet using CSS custom properties. Key design tokens are at the top of the file: color palette (ink/paper/forest-green/bronze), typography (DM Serif Display for headings, DM Sans for body), spacing, and border radii.

`static/js/main.js` — IIFE that manages the YouTube video modal on the landing page.

### Route scaffold (unimplemented stubs)

Several routes in `app.py` are placeholders with `# TODO` comments, numbered by implementation step:
- Step 3: `/logout`
- Step 4: `/profile`
- Step 7: `/expenses/add`
- Step 8: `/expenses/<id>/edit`
- Step 9: `/expenses/<id>/delete`

Authentication logic (register/login form handling) is also not yet wired to the database.

## Design system

| Token | Value |
|---|---|
| Primary text | `#0f0f0f` (ink) |
| Background | `#f7f6f3` (paper) |
| Accent green | `#1a472a` |
| Accent bronze | `#c17f24` |
| Danger | `#c0392b` |
| Max width | `1200px` |
| Auth form width | `440px` |

Responsive breakpoints: 900px, 600px.
