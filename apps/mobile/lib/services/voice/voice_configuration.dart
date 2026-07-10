/// Centralized tunables for the voice/wake pipeline.
///
/// Per the ChatGPT architecture review (item #6): thresholds, timeouts,
/// and other tunable values should live in one place instead of being
/// scattered as local constants across `wake_word_engine.dart`,
/// `live_voice_loop_io.dart`/`live_voice_loop_web.dart`, and `app_state.dart`.
/// Values below preserve the exact previous defaults (no behavior change),
/// they are just centralized.
class VoiceConfiguration {
  const VoiceConfiguration._();

  // --- Wake word engine ---
  /// Activation threshold for the v0.1 (TTS-trained) wake model.
  static const double wakeThresholdV1 = 0.05;

  /// Activation threshold for the v0.2 (real-voice trained) wake model.
  static const double wakeThresholdV2 = 0.04;

  /// Warm-up window (ms) after the mic stream starts before we begin
  /// evaluating wake activation, to let the model'"'"'s internal buffers settle.
  static const int wakeWarmupMs = 1500;

  /// Cooldown (seconds) after a wake activation before another can fire.
  static const int wakeCooldownSeconds = 2;

  // --- Android foreground wake service ---
  /// Max number of bounded auto-retries after a failed wake engine start.
  static const int wakeRetryMaxAttempts = 2;

  /// Base backoff unit between auto-retries (multiplied by attempt number).
  static const Duration wakeRetryBaseBackoff = Duration(seconds: 2);

  /// How long we wait for the FGS isolate to report `engine_ready` before
  /// treating the attempt as failed.
  static const Duration wakeEngineReadyTimeout = Duration(seconds: 8);

  /// Settle delay after force-stopping the foreground service before
  /// starting it again, to give Android time to tear down the old isolate.
  static const Duration wakeServiceRestartSettleDelay = Duration(
    milliseconds: 300,
  );

  // --- Live voice loop / VAD ---
  static const double vadThresholdDbIo = -45.0;
  static const double vadThresholdDbSpeakingIo = -32.0;
  static const double vadThresholdDbWeb = -35.0;
  static const double vadThresholdDbSpeakingWeb = -25.0;

  /// VAD tick interval (ms).
  static const int vadTickMs = 120;

  /// Default silence duration (ms) before a voiced segment is ended.
  static const int vadSilenceMs = 500;

  /// Max single segment duration (ms) before it'"'"'s force-ended.
  static const int vadMaxSegmentMs = 10000;

  // --- Conversation lifecycle ---
  /// Seconds of inactivity in an active Live conversation before it'"'"'s ended.
  static const int conversationIdleSeconds = 18;

  /// Debounce window (ms) to prevent rapid double-tap re-toggling Live.
  static const int toggleLiveDebounceMs = 300;

  /// Suppression window (seconds) applied around wake resume after Live ends.
  static const Duration wakeSuppressDuration = Duration(seconds: 3);
}
