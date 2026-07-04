# LinkedIn

> Last verified: 2026-07-04

## Authentication

- **Logged-in signal:** `document.title` contains `"Feed | LinkedIn"` on `/feed/`, or the user's name on profile pages.
- **Logged-out signal:** Redirects to `https://www.linkedin.com/login` or shows a "Join now" page.
- **Requirement:** browsectl-chrome must be launched with an already-authenticated Chrome profile. LinkedIn uses cookie-based auth; no programmatic login is attempted.

## Navigation patterns

| Page | URL pattern | Notes |
|------|-------------|-------|
| Feed | `https://www.linkedin.com/feed/` | Good login check — redirects if not authenticated |
| Own profile | `https://www.linkedin.com/in/me/` | Redirects to `/in/<slug>/?isSelfProfile=true` |
| Profile (anyone) | `https://www.linkedin.com/in/<slug>/` | Main profile view |
| Experience detail | `https://www.linkedin.com/in/<slug>/details/experience/` | Full experience list |
| Education detail | `https://www.linkedin.com/in/<slug>/details/education/` | Full education list |
| Skills detail | `https://www.linkedin.com/in/<slug>/details/skills/` | Full skills list (49 in test) |
| Languages detail | `https://www.linkedin.com/in/<slug>/details/languages/` | All languages with proficiency |

- LinkedIn is a full SPA. Navigation via `goto` triggers `Page.loadEventFired` normally.
- `/in/me/` always resolves to the authenticated user's profile.
- Detail pages (`/details/*`) show the full list without truncation.

## DOM landmarks

### Profile page (`/in/<slug>/`)

| What | Selector / method | Verified |
|------|-------------------|----------|
| Page loaded | `document.title` contains user name | 2026-07-04 |
| Name (h2) | First `h2` inside `main section` | 2026-07-04 |
| Headline | Leaf `span` containing role text near top of first `section` | 2026-07-04 |
| About text | `[data-testid=expandable-text-box]` | 2026-07-04 |
| Section headings | `main section h2` — returns: About, Experience, Education, Skills, etc. | 2026-07-04 |
| Section content | `sec.innerText` where `sec` is the `section` parent of the target `h2` | 2026-07-04 |
| "Show all" links | `a` elements with text like `"Show all 4 languages"` — href leads to detail page | 2026-07-04 |

### Detail pages (`/details/*`)

| What | Selector / method | Verified |
|------|-------------------|----------|
| Main content | `document.body.innerText` (content is outside `main` on some detail pages) | 2026-07-04 |
| List items | Search body text for known anchors (e.g. university name) and extract surrounding context | 2026-07-04 |

### General

| What | Selector / method | Verified |
|------|-------------------|----------|
| No `h1` on pages | LinkedIn uses `h2` as the highest heading inside content | 2026-07-04 |
| Obfuscated classes | Class names are hashed (e.g. `_75228706 _9d763823`), not stable — never select by class | 2026-07-04 |
| Data-testid attrs | Some elements have `data-testid` (e.g. `expandable-text-box`) — prefer these when available | 2026-07-04 |
| Element count | Profile page has ~2000+ DOM elements when fully rendered | 2026-07-04 |

## Workflows

### Extract full profile (own)

```bash
browsectl goto https://www.linkedin.com/in/me/
browsectl wait "main section" 10

# Name and headline
browsectl eval '(() => {
    const main = document.querySelector("main");
    const name = main.querySelector("h2").textContent.trim();
    const spans = main.querySelector("section").querySelectorAll("span[aria-hidden=true]");
    const texts = [];
    for (const s of spans) { const t = s.textContent.trim(); if (t.length > 10) texts.push(t); }
    return JSON.stringify({name, headline: texts[0] || ""});
})()'

# About
browsectl eval 'document.querySelector("[data-testid=expandable-text-box]")?.textContent?.trim()'

# Experience (scroll to load, then extract)
browsectl scroll 2000
browsectl eval '(() => {
    const sections = document.querySelectorAll("main section");
    for (const sec of sections) {
        const h2 = sec.querySelector("h2");
        if (h2 && h2.textContent.trim() === "Experience") return sec.innerText;
    }
    return "";
})()'

# Education, Skills, Languages — use detail pages for complete data
browsectl goto https://www.linkedin.com/in/me/details/education/
browsectl eval 'document.body.innerText'

browsectl goto https://www.linkedin.com/in/me/details/skills/
browsectl eval 'document.querySelector("main").innerText'

browsectl goto https://www.linkedin.com/in/me/details/languages/
browsectl eval 'document.querySelector("main").innerText'
```

### Check login status

```bash
browsectl goto https://www.linkedin.com/feed/
browsectl eval 'document.title.includes("Feed") ? "logged_in" : "logged_out"'
```

## Known issues / gotchas

- **No `h1` elements.** LinkedIn exclusively uses `h2`+ in content areas. `querySelector("h1")` always returns null.
- **Class names are hashed and unstable.** Never rely on class selectors like `.text-heading-xlarge` — they rotate across deployments. Use `data-testid`, semantic structure (`section h2`), or `innerText` search.
- **Sections lazy-load on scroll.** Experience, Education, Skills sections may not be fully in the DOM until you `scroll` past them. Always scroll before extracting lower sections.
- **"See more" / expandable text.** About section and experience descriptions truncate behind a button. The `[data-testid=expandable-text-box]` usually contains the full text regardless, but experience descriptions may need the detail page.
- **Detail pages are more reliable than main profile.** `/details/education/`, `/details/skills/`, `/details/languages/` show full untruncated content without needing to expand anything.
- **Rate limiting.** Rapid successive `goto` calls may trigger LinkedIn's bot detection. Add reasonable delays between navigations in automated workflows.
- **`/in/me/` redirect.** This always works for the authenticated user but the final URL will be the actual slug (e.g. `/in/luisbordo/`). Don't hardcode the slug if the tool should work for any logged-in user.
