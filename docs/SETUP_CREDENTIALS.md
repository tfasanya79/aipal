# AiPal — Credentials Setup Guide

**Purpose:** This file tells you exactly what accounts/steps are needed to activate
the features that are currently configured but not yet live.  
**Time estimate:** ~45–60 minutes total across all providers.  
**After each section:** note the values listed under "What to give back" — paste them
back to Copilot and the VM will be configured automatically.

---

## 1 — Resend (weekly email summary)

**What it enables:** `POST /daily/weekly-summary/send` — delivers the weekly
activity email to each user's inbox.

**Cost:** Free tier — 3,000 emails/month, 1 domain. Sufficient for MVP.

### Steps

1. Go to **https://resend.com** → click **Sign up** (use your work email).
2. Verify your email address.
3. On the dashboard, click **API Keys** → **Create API Key**.
   - Name: `aipal-production`
   - Permission: **Sending access**
4. Copy the key — it starts with `re_`. **You only see it once.**
5. *(Optional but recommended)* Click **Domains** → **Add Domain** → enter `aipal.io`
   (or whatever domain you own). Follow the DNS steps (adds 3 TXT/MX records).
   If you skip this, emails send from `onboarding@resend.dev` — fine for MVP testing.

### What to give back to Copilot

```
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxx
RESEND_FROM_EMAIL=weekly@aipal.io        ← or leave blank to use resend.dev default
```

---

## 2 — Google OAuth (Sign in with Google)

**What it enables:** `POST /auth/google` on the API + the "Continue with Google"
button in the mobile app.

**Cost:** Free (Google Identity Services).

### Steps

1. Go to **https://console.cloud.google.com** → select or create a project
   (e.g. `aipal-production`).
2. In the left menu: **APIs & Services** → **OAuth consent screen**.
   - User type: **External**
   - App name: `AiPal`
   - Support email: your email
   - App logo: optional
   - Scopes: click **Add or remove scopes** → add `email` and `profile`
   - Save and continue through all steps (no test users needed for now).
3. Go to **APIs & Services** → **Credentials** → **+ Create Credentials** →
   **OAuth 2.0 Client ID**.
4. Create **one client per platform**:

   **Android client:**
   - Application type: **Android**
   - Package name: `com.aipal.app` *(check `apps/mobile/android/app/build.gradle` → `applicationId`)*
   - SHA-1 certificate fingerprint: run the command below on your Mac/Linux:
     ```bash
     keytool -list -v -keystore ~/.android/debug.keystore \
       -alias androiddebugkey -storepass android -keypass android \
       | grep SHA1
     ```
     For the **release** signing key (the one used for Play Store):
     ```bash
     keytool -list -v \
       -keystore <path-to-your-release-keystore> \
       -alias <key-alias>
     ```
   - Click **Create** → copy the **Client ID** (ends in `.apps.googleusercontent.com`).

   **Web client** (needed for the API backend to verify tokens):
   - Application type: **Web application**
   - Name: `AiPal Web/API`
   - Authorised redirect URIs: `https://43.160.220.9.sslip.io/auth/google/callback`
   - Click **Create** → copy the **Client ID**.

5. The **Web client ID** is what goes into the API's `GOOGLE_CLIENT_ID` env var.
   The **Android client ID** goes into the Flutter app's `google-services.json`.

6. Download `google-services.json`:
   Go to **Project settings** (gear icon) → **Your apps** → Android app →
   **Download google-services.json**.

### What to give back to Copilot

```
GOOGLE_CLIENT_ID=xxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.apps.googleusercontent.com
                 ↑ This is the WEB client ID (used by the API to verify tokens)
```

Also upload (or paste the path to) the downloaded `google-services.json` file —
it goes into `apps/mobile/android/app/google-services.json`.

---

## 3 — Spotify (music control)

**Current policy decision (2026-06):** We dropped Spotify Web API OAuth for MVP.

**Reason:** Spotify Developer Mode now has hard limits (Premium-only dev accounts,
1 app per developer, and max 5 test users). That makes MVP test behavior diverge
from production reality and risks shipping a music feature that cannot scale.

**What we use now:** Android deep links (`spotify:` URIs) from the mobile app.
- No Spotify API keys required.
- Works with installed Spotify app.
- Commands currently supported by AiPal voice flow: open/play via search query.

### What to give back to Copilot

Nothing for Spotify credentials.

---

## 4 — Apple Sign-In (iOS App Store requirement)

**What it enables:** `POST /auth/apple` + "Continue with Apple" button in the iOS app.
**Required by Apple** for any iOS app that offers third-party social login.

**Cost:** Requires an Apple Developer account ($99/year).

> **Skip this for Android-only MVP.** Come back before App Store submission.

### Steps

1. Go to **https://developer.apple.com** → **Account** → **Certificates, IDs & Profiles**.
2. **Register an App ID** (if not done):
   - Identifiers → **+** → App IDs → App
   - Bundle ID: `com.aipal.app` *(must match your Flutter bundle ID)*
   - Capabilities: enable **Sign In with Apple**
3. **Create a Service ID** (used as `apple_client_id`):
   - Identifiers → **+** → Services IDs
   - Description: `AiPal Sign In`
   - Identifier: `com.aipal.app.signin`
   - Enable **Sign In with Apple** → Configure:
     - Primary App ID: select `com.aipal.app`
     - Domains: `43.160.220.9.sslip.io`
     - Return URL: `https://43.160.220.9.sslip.io/auth/apple/callback`
4. **Create a Key** (used to verify tokens on the backend):
   - Keys → **+** → Name: `AiPal Apple Sign In`
   - Enable **Sign In with Apple** → Configure → Primary App ID: `com.aipal.app`
   - Click **Continue** → **Register** → **Download** the `.p8` file
   - Note the **Key ID** shown on screen
5. Note your **Team ID** from the top-right of the developer portal (10-char string).

### What to give back to Copilot

```
APPLE_TEAM_ID=XXXXXXXXXX           ← 10-char string from top-right of developer portal
APPLE_CLIENT_ID=com.aipal.app.signin   ← the Service ID identifier
APPLE_KEY_ID=XXXXXXXXXX            ← Key ID from step 4
```

Also upload the `.p8` private key file (keep it secret — never commit to git).

---

## 5 — Wake phrase model v0.2 (HiPal / AiPal variants)

**What it enables:** Wake detection for "HiPal", "AiPal", "Hey Pal" in addition
to "Hi Pal". Current model only reliably triggers on "Hi Pal".

**Cost:** Free (training runs locally on the VM or any machine with Python).

### Steps — in-app wake enrollment (preferred path)

Use the app's guided Wake Enrollment flow (to be shipped in Phase 2):

1. Open **Settings → Wake enrollment**.
2. Record **5 utterances each** for:
   - "Hi Pal"
   - "HiPal"
   - "AiPal"
   - "Hey Pal"
3. Stay in a quiet room for capture; then run the built-in ambient check.
4. Save calibration — the app stores a per-user wake threshold locally.

This gives production-representative behavior without requiring external test
recording collection.

### What to give back to Copilot

No credentials needed. After enrollment ships, provide:
1. Device model + Android version used for enrollment.
2. Wake enrollment result screenshot (pass/fail + calibrated threshold).
3. Any false-wake examples (time + phrase heard).

---

## 6 — Summary: what to paste back

Once you have completed the steps above, paste **all of the following** back
to Copilot in one message, and Copilot will:
- Write the values to the VM's `/etc/default/aipal-v2` env file
- Restart the API
- Confirm each feature is live with a smoke test

```
# ── Paste this block back to Copilot ──────────────────────────────────────

RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=weekly@aipal.io          # or leave blank

GOOGLE_CLIENT_ID=...apps.googleusercontent.com
# also drop google-services.json into apps/mobile/android/app/ in the repo

# Spotify credentials are no longer required (Android deep-link mode)

# Apple — only needed before iOS App Store submission:
# APPLE_TEAM_ID=...
# APPLE_CLIENT_ID=com.aipal.app.signin
# APPLE_KEY_ID=...
# (upload the .p8 file separately)

# Wake model:
# No credential required. Share enrollment test evidence instead.

# ──────────────────────────────────────────────────────────────────────────
```

---

## Checklist

| Item | Estimated time | Priority |
|------|---------------|----------|
| Resend API key | 5 min | 🔴 High — needed for weekly emails |
| Google OAuth setup | 20 min | 🔴 High — needed for social login |
| Spotify credentials | 0 min | ✅ Not required in deep-link mode |
| Apple Sign-In | 20 min | 🟡 Medium — required for iOS, not Android |
| Wake enrollment | 15 min per user | 🟡 Medium — calibration + model retrain |

> **Quickest path to a fully working demo:**  
> Do **Resend + Google** (≈25 minutes) → paste back → Copilot deploys.
> Apple can follow later; wake enrollment runs inside the app flow.
