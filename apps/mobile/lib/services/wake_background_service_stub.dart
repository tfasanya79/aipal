/// Web/iOS stub — background wake service is Android-only (C2).
class WakeBackgroundService {
  static Future<void> init() async {}

  /// Mirrors the Android implementation's diagnostic field (always null here
  /// since this platform never attempts to run the service).
  static String? lastEnsureRunningError;

  static Future<bool> ensureRunning({bool forceRestart = false}) async => false;

  static Future<void> stop() async {}

  static void setSuppressed(bool suppressed) {}

  static void ensureListening() {}

  static Future<bool> isRunning() async => false;
}
