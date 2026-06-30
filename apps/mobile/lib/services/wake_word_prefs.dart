import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Client-side prefs for wake word (default off until user opts in).
class WakeWordPrefs {
  static const _enabledKey = 'wake_word_enabled';
  static const _introKey = 'wake_word_intro_shown';
  static const _enrolledKey = 'wake_word_enrolled';
  static const _calibratedThresholdKey = 'wake_threshold_calibrated';
  static const _storage = FlutterSecureStorage();

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
