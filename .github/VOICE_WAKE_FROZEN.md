# Voice / wake — frozen paths

Do not modify these paths without explicit **unfreeze** from the product owner.

**Freeze ≠ disable:** Half-duplex Live and wake-word must remain **enabled** with build-38 behavior. Only **code edits** to these paths are forbidden.

```
apps/mobile/lib/providers/app_state.dart     # toggleLive, wake sync, voice segment handler
apps/mobile/lib/services/live_voice_loop_io.dart
apps/mobile/lib/services/live_voice_loop.dart
apps/mobile/lib/services/wake_background_service*.dart
apps/mobile/lib/services/wake_word_service*.dart
apps/mobile/lib/services/wake_word_engine.dart
apps/api/app/modules/voice/                 # audio_turn / STT path (FROZEN surface)
```

See [`docs/releases/VOICE_BASELINE.md`](../docs/releases/VOICE_BASELINE.md).
