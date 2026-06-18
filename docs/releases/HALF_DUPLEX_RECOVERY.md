# Half-duplex recovery build (2.5.0+38)

**Branch:** `recovery/half-duplex-2.4.1`  
**Code baseline:** `f3eea7d` (2.4.1+19) + splash boot fix only  
**Date:** 2026-06-18

## What this is

Hard reset of mobile voice to pre-full-duplex half-duplex:

- `LiveVoiceLoop` → AAC segments → `POST /turn/audio` → STT → brain → TTS
- No Live Voice v2, no PCM WebSocket streaming, no client streaming STT

## One-shot test (Tim / teems5uk@gmail.com)

1. Install **2.5.0 build 38** from Play Internal
2. Settings → **Live voice engine** should not show v2 (half-duplex only)
3. Tap orb → greeting → speak one sentence → expect spoken reply
4. Resting → say **Hi Pal** → expect Live

Reply **pass** or **fail** only.

**Result:** **PASS** (Tim, 2026-06-18) — see [`VOICE_BASELINE.md`](VOICE_BASELINE.md)

## Stop rule (historical)

| Result | What happens next |
|--------|-------------------|
| **Pass** | Voice pillar unblocked; v2 stays dead; resume other features |
| **Fail** | **Stop all voice code changes.** No build 39. Options only if explicitly requested later: adb logcat, push-to-talk, or text mode |

If this build fails the test above, **no further voice builds** unless explicitly requested (adb session, push-to-talk, or text mode).

## GitHub Project sync (separate)

If `sync-project.yml` fails with **401 Bad credentials**, rotate repository secret **`PROJECT_SYNC_TOKEN`** (PAT with `repo` + `project` scopes) and re-run the workflow.
