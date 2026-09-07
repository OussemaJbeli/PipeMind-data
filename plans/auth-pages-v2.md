# Auth pages v2 — implementation plan

**Reference:** [`ui/login.png`](../ui/login.png)
**Affects:** `AuthLayout`, `LoginView`, `RegisterView`, `ForgotPasswordView`,
`ResetPasswordView`, `AcceptInvitationView`, `AuthField`
**Status:** plan only — nothing in this document has been implemented.

---

## 1. The layout is mirrored

This is the change that touches every auth view at once.

```
CURRENT                              MOCKUP
┌──────────┬───────────────────┐    ┌───────────────────┬──────────┐
│  form    │  branded panel    │    │  branded panel    │  form    │
│  480px   │  (decorative)     │    │  + illustration   │  card    │
└──────────┴───────────────────┘    └───────────────────┴──────────┘
```

Two differences that matter beyond the flip:

1. **The form is a bordered card**, not a bare column — it floats on the dark
   background with its own border, radius and padding, vertically centred.
2. **The left panel carries real content**: headline, body copy, four feature
   chips, the illustration, and a partner logo row. It is no longer decorative,
   so it can no longer be `aria-hidden` wholesale — the headline and copy are
   meaningful and should be in the reading order, while only the artwork is
   hidden.

`AuthLayout` therefore needs a `<slot name="showcase">` so each view can vary the
left side (sign-in vs invitation, say) instead of every view sharing one panel.

Below `lg` the left panel drops entirely and the card becomes the page, exactly as
now. Keep that: the form is what the user came for.

---

## 2. The form card

Reading down `ui/login.png`:

| Element | Notes |
|---|---|
| Logo + wordmark | Repeated inside the card, above the heading. `PmLogo` exists; the wordmark is currently plain text and matches well enough. |
| `Welcome back` | Already correct. |
| Sub-line | *"Sign in to your account to continue to your workspace."* |
| Email field | **Leading mail icon inside the input.** |
| Password field | **Leading lock icon + trailing eye toggle.** |
| Remember me | Lime checkbox — the native checkbox with `accent-color` is close; a custom control would match better. |
| Forgot password? | Lime link, right-aligned on the same row. Already built. |
| `→ Sign in` | Full-width, lime, `h-12`, leading arrow. Taller than the current `PmButton` `lg`. |
| `or` divider | Centred label over a hairline rule. |
| Three OAuth buttons | GitHub · GitLab · Google, each full-width with a brand mark. **See §4 — this is the one item with real backend scope.** |
| `Don't have an account? Create one` | Already built. |
| Reassurance block | Shield icon, *"Your data is protected"* + two lines on encryption. |

### `AuthField` additions

Three new optional props, all backward-compatible with the five views already
using it:

- `icon` — leading icon inside the input; adds left padding when set.
- `revealable` — for passwords: renders the eye toggle, swaps `type` between
  `password` and `text`. The button needs `aria-label` that changes with state
  and `tabindex` in natural order.
- `size` — to reach the mockup's taller inputs without changing the default.

### The reassurance block is a claim to keep true

*"We use industry-standard encryption to keep your information safe and secure."*

Defensible as written: passwords are bcrypt-hashed by Laravel, provider tokens
and AI keys use the `encrypted` cast, and the API keys are `$hidden`. Worth
knowing it is only defensible **over HTTPS** — on the current localhost HTTP
setup the sentence is aspirational. Either qualify it or make sure the deployed
site is TLS-only before it ships.

---

## 3. The showcase panel

| Element | Notes |
|---|---|
| Logo + wordmark | Larger than the card's. |
| Eyebrow | `INTELLIGENT CI/CD FAILURE ANALYSIS PLATFORM` — uppercase, wide letter-spacing, dim. |
| Headline | `From Failure` / `to Fix, Faster.` with **Faster.** in `--pm-accent`. |
| Body | Four lines of the same copy the landing hero uses. Worth keeping identical so the two pages reinforce rather than paraphrase each other. |
| Feature chips | Four inline: *Detect failures early · Analyze with AI · Recommend fixes & actions · Keep your flow*, each with a small lime icon. |
| Illustration | The large isometric scene — see assets. |
| Partner row | `Trusted by DevOps teams worldwide` + six greyscale logos. |

**The partner row has the same honesty problem as the landing page.** Presented
under "Trusted by", those logos read as customers. They are integration targets.
Retitle to *"Works with"* and it becomes true at no visual cost.

---

## 4. OAuth — the one item with real backend scope

Everything else in this document is frontend work. The three `Continue with …`
buttons are not: **no OAuth backend exists.** Today's auth is
email/password + Sanctum only.

What it would take:

1. `composer require laravel/socialite` and register GitHub, GitLab and Google
   drivers.
2. Three env credential pairs, plus registered callback URLs per provider — and
   each needs a **stable public URL**, which the current cloudflared tunnel is
   not. The tunnel hostname rotates, and every rotation breaks the callbacks.
3. A `social_accounts` table (`user_id`, `provider`, `provider_user_id`,
   `avatar_url`, unique on `(provider, provider_user_id)`), plus a migration and
   a `schema.sql` update.
4. `GET /auth/{provider}/redirect` and `GET /auth/{provider}/callback` — outside
   the `team` middleware, since a first-time OAuth user has no team yet.
5. Account-linking rules, which is where the security lives:
   - Provider email matches an existing user → link, **only if** the provider
     reports the email verified. Trusting an unverified provider email lets
     anyone who can set an email on a throwaway account take over a PipeMind one.
   - No match → create the user, then send them through `/welcome`.
   - Already signed in → link to the current user, and refuse if that provider
     identity is already attached elsewhere.
6. A `GET /auth/providers` endpoint so the buttons render only for providers that
   are actually configured. Three buttons that 500 are worse than none.

**Recommendation: build the visual redesign first and leave OAuth out.**
The buttons are roughly a third of the card's height, so their absence is
visible — but a button that fails is worse than a button that is not there, and
the redesign delivers most of the value on its own. If they must appear before
the backend exists, render them `disabled` with a `Coming soon` tooltip rather
than wiring them to nothing.

GitHub is the one to do first: every project you monitor is already there, and
the integration token flow has taught the codebase the shape of it.

---

## 5. Applying it to the other four views

`AuthLayout` and `AuthField` do most of the work; each view then needs the card
treatment and its own showcase copy.

- **RegisterView** — same card. `PasswordStrength` already exists and matches the
  mockup's spirit. Showcase headline could shift to something onboarding-shaped
  (*"Connect a repo. Break a build. Watch it explain itself."*).
- **ForgotPasswordView / ResetPasswordView** — narrower card, no OAuth block, no
  feature chips. Keep the "same answer for known and unknown addresses"
  behaviour exactly as it is; it is a security property, not a UX choice.
- **AcceptInvitationView** — the showcase should name the **inviting workspace**
  rather than generic marketing copy. Someone arriving on an invitation link has
  already been sold; they need to know which team they are joining.

---

## 6. Suggested order

1. `AuthLayout` — mirror it, add the `showcase` slot, wrap the form in a card.
   Every view improves at once.
2. `AuthField` — `icon`, `revealable`, `size`.
3. `LoginView` — full mockup treatment, minus OAuth.
4. Showcase content: eyebrow, headline, chips, "Works with" row.
5. Propagate to the other four views.
6. Illustration, when the asset exists.
7. OAuth, as a separate piece of work with its own decisions.

Steps 1–5 need **no new artwork** and close most of the gap. The illustration
slots into a reserved space afterwards.

---

## 7. Assets required

### Must have

| # | Asset | Notes |
|---|---|---|
| 1 | **Auth illustration** — transparent PNG/WebP, ≥ 2000 px wide | The isometric scene in `ui/login.png`: push → providers → cube → Build Failed → AI Analysis → Fix Applied. Transparent so it composes over the panel gradient. Distinct from the landing hero art (different composition), though the same visual family. If only one render can be made, **make it this one** — it tells the whole product story in a single image and could be reused, cropped, on the landing page. |

### Nice to have

| # | Asset | Notes |
|---|---|---|
| 2 | **Ambient background** — subtle green/dark gradient or mesh, 2560 × 1440 | The panel's soft glow. A CSS radial-gradient gets ~80 % of the way; the asset is polish. |
| 3 | **Wordmark lockup** — SVG, logo + "PipeMind" set together | Currently `PmLogo` plus a text span. Fine at these sizes, but a proper lockup would sharpen the header. |

### Not needed — already available

- GitHub, GitLab, Google, Jenkins, AWS, Microsoft, Google Cloud marks —
  `simple-icons` is already wired through `unplugin-icons`.
- Mail, lock, eye, shield and every chip icon — `lucide`, likewise.

### Decisions needed from you

1. **OAuth** — build it, omit the buttons, or show them disabled? (§4)
2. **Partner row** — retitle to "Works with"? (§3)
3. **One illustration or two?** Asset #1 here and #1 in the landing plan are
   different compositions. One good render reused in both is a reasonable
   trade-off if commissioning is a constraint.
4. **Encryption copy** — keep as written and ensure TLS at deploy, or soften it
   while the app is HTTP-on-localhost? (§2)
5. **Light theme** — both mockups are dark-only. Auth currently themes correctly;
   should that survive the redesign or is dark-only acceptable here too?
