# AiPal — Deploy Guide

## SSH access

Always connect via the configured alias — never use a bare IP with a manual key path:

```bash
ssh aipal-vm          # ✅ correct
ssh dev@43.160.220.9  # ❌ will fail (wrong key)
```

The alias is defined in `~/.ssh/config`:
```
Host aipal-vm
  HostName 43.160.220.9
  User dev
  IdentityFile ~/.ssh/aipal_copilot_ed25519
  IdentitiesOnly yes
```

---

## Standard deploy sequence (after any code change)

### 1 — Push code to GitHub
```bash
# On Windows (local dev machine)
git push origin main
```

### 2 — Deploy API to VM
```bash
ssh aipal-vm "cd ~/aipal && git pull origin main && \
  sudo rsync -a --delete \
    --exclude=.venv --exclude=__pycache__ --exclude='.env' \
    ~/aipal/apps/api/ /opt/aipal-v2/apps/api/ && \
  sudo systemctl restart aipal-v2 && \
  sudo systemctl status aipal-v2 --no-pager -l"
```

### 3 — Deploy Android to Play Internal
```bash
ssh aipal-vm "cd ~/aipal && git pull origin main && bash scripts/deploy-android-internal.sh"
```

> **This must be done after every feature or fix** so the Play Internal track is
> always up to date for functional testing.

The script (`scripts/deploy-android-internal.sh`) handles:
- `flutter build appbundle --release`
- Signs with the upload keystore (`~/.secrets/aipal-upload-keystore.jks`)
- Uploads via fastlane to Play Internal track using `~/.secrets/play-api.json`

---

## Bump the version before deploying

Edit `apps/mobile/pubspec.yaml`:
```yaml
version: X.Y.Z+N    # increment N (build number) every Play upload
```
Play Console rejects uploads with the same build number.

---

## VM credentials location

| File | Purpose |
|------|---------|
| `~/aipal/.secrets/play-api.json` | Google Play service account (fastlane upload) |
| `~/aipal/.secrets/android-signing.env` | Keystore path + passwords |
| `~/aipal/.secrets/aipal-upload-keystore.jks` | Release signing keystore |
| `/opt/aipal-v2/.env` | API runtime environment variables |

**Never commit any file from `~/aipal/.secrets/` to git.**

---

## VM toolchain paths

| Tool | Path |
|------|------|
| Flutter | `/opt/flutter/bin/flutter` |
| fastlane | `/usr/local/bin/fastlane` |
| Java 17 | `/usr/lib/jvm/java-17-openjdk-amd64` |
| Android SDK | `/opt/android-sdk` |

---

## GitHub Actions (CI only — not deploy)

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `api-ci.yml` | Push to `apps/api/**` | Run API tests |
| `mobile-ci.yml` | Push to `apps/mobile/**` | `flutter analyze` + `flutter test` |
| `release-android.yml` | Push tag `mobile/vX.Y.Z` | Build AAB, save as artifact |

CI **does not** upload to Play — that is always done via `deploy-android-internal.sh` on the VM.

---

## Smoke test after deploy

```bash
ssh aipal-vm "cd ~/aipal && bash scripts/smoke-test.sh"
```

Or manually:
```bash
BASE=https://43.160.220.9.sslip.io/api/v2
curl -sf $BASE/health
curl -sf $BASE/voice/catalogue | python3 -m json.tool
```
