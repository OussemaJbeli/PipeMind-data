# Landing page v2 — implementation plan

**Reference:** [`ui/landingPage.png`](../ui/landingPage.png)
**Replaces:** `PipeMind-front/src/views/public/LandingView.vue` (built 2026-09-07)
**Status:** plan only — nothing in this document has been implemented.

---

## 1. Where the current page falls short

The existing `LandingView` has the right *skeleton* — hero, problem, how-it-works,
features, privacy, CTA, footer — and the right substance. What it lacks is
everything that makes the mockup look like a product rather than a README:

| | Current | Mockup |
|---|---|---|
| Nav | logo + Sign in + Get started | 5 nav links, theme toggle, two CTAs |
| Hero art | `HeroDemo` — a typed terminal animating into the real `AnalysisPanel` | A 3-D isometric render of the whole pipeline |
| Hero CTAs | two buttons | two buttons **+ three trust ticks** |
| Sections | 6 | 8 (adds integrations, product screenshot, social proof) |
| Decoration | none | orbit graphic, glowing connectors, CTA wave art |
| Social proof | none | 6 partner logos + a rotating testimonial |
| Footer | one line | 4-column sitemap + social icons |

**The single biggest visual gap is the hero.** Everything else is layout work.

**Keep `HeroDemo`.** It shows the real `AnalysisPanel` with static data, which is
a stronger claim than any render: it *is* the product output. The mockup's 3-D art
should sit **behind or beside** it, not replace it. Losing it would trade a true
demonstration for a picture of one.

---

## 2. Brand spelling — decide before building

The mockup says **PipMind** in the nav, hero and footer. Everything else in the
project — the login mockup included — says **PipeMind**.

This needs settling before any copy is written, because it lands in the `<title>`,
the OG tags, the logo lockup and eventually a domain. Assumed **PipeMind** unless
told otherwise; if the intent is a rename, it is a find-and-replace across all
four repositories plus the seeded team name.

---

## 3. Section-by-section

### 3.1 Sticky nav

```
◆ PipeMind    Home  Features  Integrations  Pricing  About      ☀  [Sign In]  [Get Started Free →]
```

- Anchor links (`#features`, `#integrations`) with `scroll-behavior: smooth` and
  `scroll-margin-top` on each section so the sticky bar never covers a heading.
- Active-section underline driven by `useIntersectionObserver` — not scroll
  offsets, which drift as content changes.
- **Pricing and About have no page.** Either cut them from the nav or make them
  anchors to real sections. A nav link to a 404 is worse than a shorter nav.
- Theme toggle reuses `ui.toggleTheme()`. The mockup is dark-only; the light
  palette needs a pass, or the toggle should be omitted here.
- Collapses to a hamburger sheet below `md`.

### 3.2 Hero

- Eyebrow pill: `🚀 AI-Powered CI/CD Failure Analysis` — lime border, translucent fill.
- Headline: `Fix CI/CD Failures` / `Faster with AI.` with **Faster** in `--pm-accent`.
  `text-4xl` → `text-6xl` at `lg`, `leading-[1.05]`.
- Body: keep the current copy, it is stronger than the mockup's.
- CTAs: lime `Get Started Free`, dark `▶ Watch Demo`.
  **There is no demo video.** Either point it at `#product` (the screenshot
  section) and relabel to "See it in action", or cut it. A play button that opens
  nothing is a broken promise in the first screenful.
- Trust row: three `i-lucide-check` ticks — *No credit card required · Setup in
  minutes · Works with your tools*. All three are true and cost nothing to say.
- Two-column at `lg`, stacked below, art first on mobile.

### 3.3 Why — features grid

- Pill `Why PipeMind?`, heading `Smart Analysis. Real Impact.`, lede.
- 3 × 2 grid of six features. Each: a rounded icon tile with a per-feature accent,
  bold title, two-line description.
- Reuse `PmIconTile`; it already does the tinted-square treatment.
- The mockup's six are close to the truth, with one fix: **"Actionable Fixes …
  (or auto-fix)"** must lose the auto-fix claim. PipeMind generates and displays
  patches; it does not apply them, and remediation (file 18) is unbuilt. Suggest
  *"Get a real diff — the exact line, not 'check your recent changes'."*
- Right-hand orbit graphic is decorative: `aria-hidden`, and the first thing to
  drop at narrow widths.

### 3.4 Integrations

- Pill, heading `Connect Your CI/CD Tools`, lede.
- Provider tiles: GitLab, GitHub, Jenkins, GitHub Actions, `+ More`.
  Use `simple-icons` via the existing `unplugin-icons` resolver — already
  configured, so no new asset for the logos themselves.
- Right: three connected cards (*Code Push → Pipeline Monitor → Analysis & Fix*)
  joined by glowing curves. The curves should be **one inline SVG with
  `stroke-dasharray` animation**, not an image — it stays crisp, themes correctly,
  and respects `prefers-reduced-motion`.

### 3.5 Product screenshot — "Complete visibility, full control"

- Left: the app in a browser chrome frame. Right: pill, heading, lede, five lime
  ticks, outline `Explore the Platform →`.
- **Take this screenshot from the real running app**, not a mockup crop: it is
  the most load-bearing honesty in the page, and a fabricated dashboard is the
  one thing a reviewer will check. The workspace and project boards are built and
  populated, so this is a real capture.
- Serve at 2× in WebP with an explicit `width`/`height` to avoid layout shift.

### 3.6 Social proof

- `Trusted by DevOps Teams Worldwide` + greyscale logo row + testimonial card
  with avatar, name, role, and carousel dots.
- **This section cannot ship as drawn.** PipeMind has no users, and the mockup
  names real companies (GitLab, HashiCorp, AWS, Microsoft, DigitalOcean, Docker)
  and an invented person ("Sarah Chen, DevOps Engineer @ Acme Corp"). Presented as
  endorsement that is a straightforward false claim, and for an academic project
  it is the kind of thing that turns a viva into a problem.

  Two honest replacements:
  - **Recast as compatibility** — retitle to *"Works with the tools you already
    run"* and keep the logos as integration targets, which is true. Drop the
    testimonial.
  - **Recast as measurement** — replace the whole band with the real numbers from
    `experiments/`: *4.1 s median analysis · $0.0015 per failure · 100 % of
    evidence citations verifiable*. Stronger than a fake quote, and it is
    genuinely unusual to show.

  Recommend the second, with the logo row from the first.

### 3.7 Closing CTA

- Full-width band, pill `Get Started`, heading `Ready to make your CI/CD
  smarter?`, lede, lime `Start Free Trial →`, `No credit card required`.
- **"Free Trial" implies paid tiers that do not exist.** Use `Get Started Free`,
  matching the nav.
- Background wave art on both flanks — see assets.

### 3.8 Footer

- Logo + tagline; columns Product / Company / Resources; social icons; copyright.
- Every link must resolve. Anything without a destination should be plain text or
  omitted — a sitemap of dead links reads worse than a small honest footer.

---

## 4. Technical notes

**Performance (Lighthouse ≥ 90).** The page is currently one route-level chunk
and fast. The risk is entirely in the new imagery:

- Every raster asset in WebP or AVIF with a JPEG fallback, `loading="lazy"`
  below the fold, `fetchpriority="high"` on the hero only.
- Explicit `width`/`height` on all of them — the mockup's imagery is large enough
  that CLS is the likely failure.
- Inline SVG for the connectors and orbit; never an `<img>`.
- No new font. The current stack is a system stack and costs nothing.

**Motion.** Section reveals via `useIntersectionObserver` + a `translate-y`
transition. Every animation — including `HeroDemo` — must no-op under
`prefers-reduced-motion: reduce`. `HeroDemo` already does.

**SEO.** `<title>`, `<meta name="description">`, OG and Twitter cards, plus a
`SoftwareApplication` JSON-LD block. Set them in the component, or add
`@unhead/vue` if more pages need it later.

**Accessibility.** Decorative art `aria-hidden`. Contrast checked on lime-on-dark
at small sizes — `--pm-accent` on `--pm-bg` is fine for headings, marginal for
11 px body text. Keyboard path through nav → hero CTAs → each section CTA →
footer, with a visible focus ring throughout.

---

## 5. Suggested order

1. Nav, hero layout, trust ticks — the first screenful carries most of the value.
2. Features grid and integrations (pure layout, no assets needed).
3. Product screenshot section — needs the capture but nothing drawn.
4. Social proof, recast as measurement.
5. Closing CTA and footer.
6. Motion, SEO, accessibility pass.

Steps 1–3 and 5 are achievable with **no new artwork at all** and would close
most of the gap. The 3-D art is polish, not a blocker.

---

## 6. Assets required

Nothing below can be produced in CSS, and each would otherwise have to be faked
or dropped.

### Must have

| # | Asset | Notes |
|---|---|---|
| 1 | **Hero 3-D render** — transparent PNG or WebP, ≥ 2400 px wide, and ideally a second cut for light theme | The isometric pipeline-with-brain scene. The single largest visual gap. Transparent background so it composes over the page gradient rather than sitting in a box. |
| 2 | **Product screenshot** — 2× PNG, 2560 × 1600, captured from the running app | Workspace or project board with real seeded data. Not a mockup crop. |

### Nice to have

| # | Asset | Notes |
|---|---|---|
| 3 | **Orbit / lightning graphic** (§3.3 right) | Could be built as inline SVG instead, at maybe 70 % of the mockup's richness. Say which you prefer. |
| 4 | **CTA band wave art** — wide transparent PNG, ~2400 × 600, or two flank pieces | The colourful ribbon behind the closing CTA. A CSS mesh gradient could approximate it but would not match. |
| 5 | **OG / social preview image** — 1200 × 630 PNG | For link unfurls. Can be a crop of #1 with the wordmark. |
| 6 | **Favicon set** — 32/180/512 px + `site.webmanifest` | `PmLogo` exists as a component; these need to be files. |

### Not needed — already available

- Provider logos (GitLab, GitHub, Jenkins, AWS, Microsoft, Docker, DigitalOcean,
  HashiCorp) — `simple-icons` is already wired through `unplugin-icons`.
- All UI icons — `lucide` likewise.
- Testimonial avatar — the section is recommended for removal.

### Decisions needed from you

1. **PipMind or PipeMind?** (§2)
2. **Social proof** — recast as compatibility, as measurement, or keep as drawn?
   (I would not ship it as drawn.)
3. **"Watch Demo"** — is there to be a video, or should it scroll to the
   screenshot?
4. **Pricing / About** nav links — real sections, or cut?
5. **Light theme** — does the landing page need one, or is dark-only acceptable
   and the toggle dropped?
