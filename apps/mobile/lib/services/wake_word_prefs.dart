import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Client-side prefs for wake word (default off until user opts in).
class WakeWordPrefs {
  static const _enabledKey = 'wake_word_enabled';
  static const _introKey = 'wake_word_intro_shown';
  static const _enrolledKey = 'wake_word_enrolled';
  static const _calibratedThresholdKey = 'wake_threshold_calibrated';
  // Round 10 Phase 3: see the matching comment in app_state.dart -- this
  // self-heals the Android Keystore BadPaddingException/BAD_DECRYPT failure
  // that was misreported as "greetingError=fetch failed" (introShown() lives
  // in the same try block as the greeting fetch, so its real exception was
  // being mislabeled).
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(resetOnError: true),
  );

  static Future<bool> isEnabled() async {
    final v = await _storage.read(key: _enabledKey);
    return v == 'true';
  }

  static Future<void> setEnabled(bool value) async {
    await _storage.write(key: _enabledKey, value: value ? 'true' : 'false');
  }

  static Future<bool> introShown() async {
    final v = await _storage.read(key: _introKey);
    return v == 'true';
  }

  static Future<void> markIntroShown() async {
    await _storage.write(key: _introKey, value: 'true');
  }

  static Future<bool> isEnrolled() async {
    final v = await _storage.read(key: _enrolledKey);
    return v == 'true';
  }

  static Future<void> markEnrollmentDone() async {
    await _storage.write(key: _enrolledKey, value: 'true');
  }

  /// Returns the per-user calibrated threshold, or null if not yet calibrated.
  static Future<double?> getCalibratedThreshold() async {
    final v = await _storage.read(key: _calibratedThresholdKey);
    if (v == null) return null;
    return double.tryParse(v);
  }

  /// Saves a per-user calibrated threshold derived from enrollment recordings.
  static Future<void> setCalibratedThreshold(double value) async {
    await _storage.write(key: _calibratedThresholdKey, value: value.toString());
  }

  static Future<void> clearCalibration() async {
    await _storage.delete(key: _calibratedThresholdKey);
    await _storage.delete(key: _enrolledKey);
  }
}
