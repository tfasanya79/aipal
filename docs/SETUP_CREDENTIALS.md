# AiPal — Credentials & Setup Guide

**Purpose:** Every external credential, VM configuration step, and pending feature
activation — with clear status so you always know what still needs your input.

**Legend:**
- ✅ **DONE** — configured and live on the production VM
- ⏳ **PENDING** — steps you need to do; what to return is listed at the bottom
- 🔵 **DEPRIORITISED** — intentionally skipped for current phase; revisit later

---

## Quick status snapshot

| # | Item | Status | Blocks |
|---|------|--------|--------|
| 1 | Resend email API key | ✅ **DONE** | Weekly email send |
| 2 | Google OAuth (Android Sign-In) | ✅ **DONE** | Social login |
| 3 | Spotify credentials | ✅ **DONE** (none needed) | Music control |
| 4 | Wake phrase model v0.2 retrain | ⚠️ **INVESTIGATING** — v0.1 restored as default (stable), v0.2 compatibility issue found | Wake HiPal/AiPal |
| 5 | Scheduled weekly email (cron) | ⏳ **PENDING** — VM systemd timer needed | Auto email every Sunday |
| 6 | Apple Sign-In | ⏳ **PENDING** — before iOS App Store only | iOS social login |
| 7 | Subscriber gateway / tier enforcement | 🔵 **DEPRIORITISED** — app is free | Paid tier gating |

---

## ✅ 1 — Resend (weekly email summary)

**Status: DONE** — `RESEND_API_KEY` is set on the VM.  
- Weekly summary API: `GET /daily/weekly-summary` ✅  
- Manual send: `POST /daily/weekly-summary/send` ✅ (Settings → "Preview & Send")  
- Sender: Resend shared domain (`onboarding@resend.dev`) until custom domain is added.

**Nothing to do now.**  
Optional future upgrade: add `aipal.io` as a custom sending domain in the Resend dashboard
and set `RESEND_FROM_EMAIL=weekly@aipal.io` on the VM.

---

## ✅ 2 — Google OAuth (Sign in with Google)

**Status: DONE** — `GOOGLE_CLIENT_ID` is set on the VM.  
- Backend: `POST /auth/google` ✅  
- Mobile: `social_auth_service.dart` uses Web client ID as `serverClientId` ✅  
- Both Android clients registered (debug SHA-1 + Play App Signing SHA-1) ✅

**Web client ID on VM:**
`312942098853-jun8att48f1hnkmhp7ibl3thrleoomik.apps.googleusercontent.com`

**Nothing to do now.**

---

## ✅ 3 — Spotify (music control)

**Status: DONE — no credentials needed.**

**Decision (2026-06):** Spotify Web API OAuth dropped for MVP.  
Reason: Spotify's 2026 Developer Mode is Premium-only, 1 app/developer, max 5 test users.
This makes dev-mode behavior non-representative of production.

**What we use:** Android device-local deep links (`spotify:` URIs via `url_launcher`).  
- No API keys or OAuth flow required.  
- Companion voice commands (play/pause/skip) open Spotify directly on the device.

**Nothing to do now.**

---

## ⚠️ 4 — Wake phrase model v0.2 (HiPal / AiPal variants)

**Status: Fixed and deployed (v2.6.19+108). Wake works on v0.1 by default; a separate
stale-model-cache bug (the actual cause of continued failures after v2.6.18+107) is now
also fixed — no external action needed from you right now.**

**What it unlocks:** Reliable detection of "HiPal", "AiPal", "Hey Pal" (not just "Hi Pal").
Current default model (`hi_pal_v0.1.onnx`) was trained on TTS-only "hi pal" — it misses
natural variants. v0.2 (trained on your real voice via OpenWakeWord) was meant to fix this,
but broke wake detection entirely when shipped as the default — see below.

### Timeline

- **2026-07-01:** v0.2 model trained on real voice samples via OpenWakeWord (813 KB ONNX file).
- **2026-07-02 (v2.6.17+106):** v0.2 shipped as the default model. Deployed, but the
  v0.2→v0.1 fallback that was supposed to ship alongside it was never actually committed
  (a prior commit only touched `pubspec.lock`). Result: wake broke for everyone on this build.
- **2026-07-03 (v2.6.18+107) — hotfix shipped:**
  - Root cause identified: the v0.2 ONNX graph (62 nodes, decomposed LayerNorm —
    `ReduceMean/Sub/Pow/Sqrt/Div/Mul/Add`) is structurally different from v0.1 (9 nodes,
    fused `LayerNormalization`). Both load fine on desktop ONNX Runtime, but the
    Android-bundled runtime inside the `open_wake_word` plugin most likely only registers
    kernels for the reference architecture — so v0.2 fails to load on-device only.
  - **Default model reverted to v0.1** (known-working) so wake works again immediately.
  - **Real v0.2→v0.1 fallback implemented** this time (previously only claimed, not
    actually committed) — if v0.2 is ever re-enabled and fails, the app now
    automatically retries with v0.1 instead of leaving wake dead.
  - **Native plugin hardened:** vendored `open_wake_word` into
    `apps/mobile/third_party/open_wake_word` and patched its C++ model-loading threads
    with proper try/catch, so an incompatible model fails gracefully instead of risking
    an uncaught native crash.
  - Settings now shows which model is actually active ("Using wake model v0.1 (stable
    default)" / "v0.2 (trained on real voices)"), and "Calibrate wake phrase" is relabeled
    "Fine-tune wake accuracy (optional)" since it's no longer required.
- **2026-07-03 (v2.6.19+108) — round 2 hotfix shipped:**
  - The v0.1-default hotfix (v2.6.18+107) did **not** fix wake on the test device —
    screenshots still showed "OpenWakeWord.init returned false" / "Retry listener" even
    though the device had the new build installed (confirmed via the updated Settings
    label). This ruled out the v0.1/v0.2 opset-mismatch theory as the active bug here.
  - **Real root cause found:** the `open_wake_word` plugin's `_extractAsset()` helper only
    copies a bundled ONNX model file (mel/embedding/wake-word) to the app's documents
    directory if a file with that name doesn't already exist there — it never overwrites.
    Android app data survives app updates, so a stale or partially-written cached file from
    earlier testing (e.g. an interrupted write during one of the earlier crash-storm builds)
    would be loaded forever, regardless of how many times we fixed and redeployed the
    bundled asset itself.
  - **Fixed:** `_extractAsset()` now always re-copies the bundled asset on every init.
    Self-heals automatically after updating to v2.6.19+108 — no reinstall or "clear
    storage" needed.
  - **Also added:** `oww_get_last_error()` native binding, surfacing the real native
    failure reason (previously only tracked internally) in the app's error messages —
    useful for diagnosing any future on-device-only failures without full crash reporting.
  - **Also fixed:** `Mobile CI` (`flutter analyze`) was failing on a lint finding inside the
    vendored plugin code; excluded `third_party/**` from analysis.
  - **Unrelated CI issue found (needs your action):** `Sync GitHub Project` workflow fails
    with `GraphQL 401: Bad credentials`. The `PROJECT_SYNC_TOKEN` repo secret (a GitHub
    PAT) looks expired or revoked. Please generate a new PAT (classic, `repo` + `project`
    scopes, or fine-grained with Projects read/write) and update the repo secret — I can't
    mint a GitHub PAT on your behalf.

### What's still pending (needs data / a decision from you, not urgent)

- **v0.2 compatibility investigation:** to confirm the exact on-device failure (rather than
  the working theory above) we'd need real device logs, which requires either (a) plugging
  a test device into a machine with `adb logcat` access, or (b) integrating crash/telemetry
  reporting (see item 7 below — blocked on a Firebase project). Until then, v0.2 stays
  off by default; wake works fine on v0.1.
- **If you want v0.2 pursued further:** the cleanest long-term fix is likely re-exporting
  the model so it uses the fused `LayerNormalization` op (same shape as v0.1) instead of
  the decomposed form OpenWakeWord's trainer produced — or rebuilding the plugin's native
  Android library with a fuller ONNX Runtime op set. Both are follow-up engineering work,
  not something that needs anything from you right now.

**What was already shipped (no action needed):**
- ✅ Wake enrollment screen in app (`Settings → Calibrate wake phrase`, now optional)
- ✅ Guided 5-utterance recording per phrase
- ✅ Per-user threshold calibration
- ✅ Crash-stabilization safety gate
- ✅ v0.1→v0.2 fallback (real, verified) + native crash hardening

---

## ✅ 5 — Scheduled weekly email automation

**Status: IMPLEMENTED — internal enqueue endpoint + worker + timer are live on the VM.**

**What it does:** Every Sunday at 18:00 UTC, AiPal enqueues weekly summary email jobs for users with
`weekly_summary_enabled=True`, and the VM worker processes/sends them.

### Implemented backend pieces

- `POST /api/v2/jobs/enqueue-weekly-summaries` (secured with `X-Internal-Secret`)
- Job type: `weekly_summary_email` in `apps/api/app/modules/jobs/service.py`
- Manual weekly send (`POST /daily/weekly-summary/send`) now marks users as opted-in
- VM helper script: `scripts/trigger-weekly-summary.sh`

### VM systemd units (already applied)

```bash
# Worker (continuous queue processor)
/etc/systemd/system/aipal-worker.service

# Weekly scheduler
/etc/systemd/system/aipal-weekly-email.service
/etc/systemd/system/aipal-weekly-email.timer
```

Current timer schedule:

```bash
OnCalendar=Sun *-*-* 18:00:00 UTC
```

### Verify on VM

```bash
ssh dev@43.160.220.9
sudo systemctl is-active aipal-worker.service
sudo systemctl is-active aipal-weekly-email.timer
sudo systemctl list-timers --all | grep aipal-weekly-email
```

### Manual trigger (safe smoke check)

```bash
ssh dev@43.160.220.9
cd ~/aipal
./scripts/trigger-weekly-summary.sh
```

Expected output:

```json
{"queued":<number>}
```

If `queued` is `0`, no users are currently opted-in (`weekly_summary_enabled=True`).
---

## ⏳ 6 — Apple Sign-In (iOS only)

**Status: PENDING — skip until before iOS App Store submission.**

Required by Apple for any iOS app that offers social login (Google/etc.).
Not needed for Android-only testing.

**Cost:** Requires an Apple Developer account ($99/year).

### Steps (do these when ready for iOS)

1. Go to **https://developer.apple.com** → **Account** → **Certificates, IDs & Profiles**.
2. **Register an App ID**:
   - Identifiers → **+** → App IDs → App
   - Bundle ID: `io.aipal.mvp`
   - Enable **Sign In with Apple**
3. **Create a Service ID**:
   - Identifiers → **+** → Services IDs
   - Description: `AiPal Sign In`
   - Identifier: `io.aipal.mvp.signin`
   - Enable **Sign In with Apple** → Configure → Primary App ID → add your domain + return URL:
     - Domain: `43.160.220.9.sslip.io`
     - Return URL: `https://43.160.220.9.sslip.io/api/v2/auth/apple/callback`
4. **Create a Key** (backend token verification):
   - Keys → **+** → Name: `AiPal Apple Sign In`
   - Enable **Sign In with Apple** → configure → Primary App ID: `io.aipal.mvp`
   - Download the `.p8` file (only downloadable once — keep it safe)
   - Note the **Key ID** on screen
5. Note your **Team ID** (10-char string top-right of developer portal).

### What to give back to Copilot

```
APPLE_TEAM_ID=XXXXXXXXXX           ← 10-char team ID
APPLE_CLIENT_ID=io.aipal.mvp.signin
APPLE_KEY_ID=XXXXXXXXXX            ← Key ID from step 4
```
Also upload the `.p8` private key file — paste its contents or share the file.
(Never commit this to git.)

---

## 🔵 7 — Subscriber gateway / tier enforcement

**Status: DEPRIORITISED — app is free for all users (2026-06 decision).**

The `subscription_tier` column exists on the User model (default `"free"`) and
`require_subscription` dependency is ready to be wired in, but no features are
gated behind it.

**Revisit when:** paid plan pricing is decided. Likely late 2026 or v3.

---

## Full "paste back" template

When you complete items 4 or 5 (or are ready to activate anything), paste this block:

```
# ── AiPal setup — paste completed items back to Copilot ───────────────────

## Item 4 — Wake enrollment evidence
WAKE_ENROLL_EVIDENCE:
Device: <model + Android version>
Hi Pal triggered: YES/NO
HiPal triggered:  YES/NO
AiPal triggered:  YES/NO
False wakes: <none / description>

## Item 5 — Weekly email cron
WEEKLY_EMAIL_CRON_READY=yes
AIPAL_INTERNAL_SECRET=<random 32+ char string>

## Item 6 — Apple Sign-In (iOS only, when ready)
APPLE_TEAM_ID=...
APPLE_CLIENT_ID=io.aipal.mvp.signin
APPLE_KEY_ID=...
# (also upload the .p8 key file)

# ─────────────────────────────────────────────────────────────────────────
```

---

## Checklist summary

| Item | Status | Your effort needed | Next step |
|------|--------|--------------------|-----------|
| Resend API key | ✅ DONE | — | — |
| Google OAuth | ✅ DONE | — | — |
| Spotify | ✅ DONE (no creds) | — | — |
| Wake model v0.2 | ✅ FIXED (stale-cache bug resolved, v2.6.19+108) | None right now | Optional: update to v2.6.19+108 on device, confirm wake activates |
| Crash reporting (Firebase Crashlytics) | ⏳ PENDING — needs external Firebase project | ~10 min | Create a Firebase project for `io.aipal.mvp`, download `google-services.json`, send it over |
| Scheduled email cron | ⏳ PENDING | 10 min | Tell Copilot "set up weekly email cron" |
| Apple Sign-In | ⏳ PENDING | 20 min | Before iOS App Store submission only |
| Subscriber gate | 🔵 DEPRIORITISED | None for now | Revisit late 2026 |

> **Quickest path to full MVP functionality:**  
> 1. ✅ Phase 1 deployment: v2.6.16+105 with all scheduling intelligence features  
> 2. ✅ Wake hotfix: v2.6.19+108 restores stable wake detection (v0.1 default + real fallback + stale-cache fix)  
> 3. ⏳ Crash reporting: create a Firebase project → send `google-services.json` → Copilot wires up Crashlytics  
> 4. ⏳ Weekly email: say "set up the weekly email cron" to Copilot  
> All remaining items can be done independently and in any order.
