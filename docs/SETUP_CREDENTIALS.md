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

**Status: v0.1 restored as the stable default (v2.6.18+107). v0.2 root cause found, fix
in progress — no external action needed from you right now.**

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

## ⏳ 5 — Scheduled weekly email automation

**Status: PENDING — needs a systemd timer configured on the VM.**

**What it unlocks:** Every Sunday at ~8 PM (user's local time) AiPal automatically
sends the weekly summary email to every user who has enabled it — without any manual action.

The API endpoint and email template are already built. Only the cron trigger is missing.

### Steps for you to do on the VM

SSH into the VM and run the following commands:

**Step 5-A: Create the systemd service unit**
```bash
ssh dev@43.160.220.9
sudo tee /etc/systemd/system/aipal-weekly-email.service > /dev/null << 'EOF'
[Unit]
Description=AiPal weekly summary email batch

[Service]
Type=oneshot
User=dev
ExecStart=/usr/bin/curl -sf -X POST http://127.0.0.1:8102/api/v2/jobs/enqueue-weekly-summaries \
  -H "X-Internal-Secret: $AIPAL_INTERNAL_SECRET"
EOF
```

**Step 5-B: Create the systemd timer unit**
```bash
sudo tee /etc/systemd/system/aipal-weekly-email.timer > /dev/null << 'EOF'
[Unit]
Description=Run AiPal weekly email every Sunday 8 PM UTC

[Timer]
OnCalendar=Sun *-*-* 18:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

**Step 5-C: Enable and start the timer**
```bash
sudo systemctl daemon-reload
sudo systemctl enable aipal-weekly-email.timer
sudo systemctl start aipal-weekly-email.timer
sudo systemctl list-timers | grep aipal
```

You should see a line showing next trigger time for the timer.

> **Note on internal secret:** The `/jobs/enqueue-weekly-summaries` endpoint needs
> an internal auth header. Tell Copilot to implement this — it's a single `X-Internal-Secret`
> header check in `config.py`. The secret value is your choice (any random string).

### What to give back to Copilot

When you're ready to enable this, tell Copilot:
```
WEEKLY_EMAIL_CRON_READY=yes
AIPAL_INTERNAL_SECRET=<any random string you choose, e.g. 32+ char hex>
```
Copilot will:
1. Add the internal secret check to the enqueue endpoint.
2. Set the secret on the VM.
3. Create the systemd units above automatically.
4. Verify the timer is registered.

**Or just say "set up the weekly email cron" and Copilot will handle all of it.**

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
| Wake model v0.2 | ⚠️ INVESTIGATING (v0.1 stable default restored, v2.6.18+107) | None right now | Optional: test v2.6.18+107 on device, confirm wake works |
| Crash reporting (Firebase Crashlytics) | ⏳ PENDING — needs external Firebase project | ~10 min | Create a Firebase project for `io.aipal.mvp`, download `google-services.json`, send it over |
| Scheduled email cron | ⏳ PENDING | 10 min | Tell Copilot "set up weekly email cron" |
| Apple Sign-In | ⏳ PENDING | 20 min | Before iOS App Store submission only |
| Subscriber gate | 🔵 DEPRIORITISED | None for now | Revisit late 2026 |

> **Quickest path to full MVP functionality:**  
> 1. ✅ Phase 1 deployment: v2.6.16+105 with all scheduling intelligence features  
> 2. ✅ Wake hotfix: v2.6.18+107 restores stable wake detection (v0.1 default + real fallback)  
> 3. ⏳ Crash reporting: create a Firebase project → send `google-services.json` → Copilot wires up Crashlytics  
> 4. ⏳ Weekly email: say "set up the weekly email cron" to Copilot  
> All remaining items can be done independently and in any order.
