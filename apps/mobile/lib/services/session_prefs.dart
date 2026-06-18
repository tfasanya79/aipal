import 'package:shared_preferences/shared_preferences.dart';

class SessionPrefs {
  static const _recordKey = 'record_test_sessions';
  static const _phaseTagKey = 'session_phase_tag';

  static Future<bool> isRecordingEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_recordKey) ?? true;
  }

  static Future<void> setRecordingEnabled(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_recordKey, value);
  }

  static Future<String?> phaseTag() async {
    final prefs = await SharedPreferences.getInstance();
    final tag = prefs.getString(_phaseTagKey);
    if (tag == null || tag.trim().isEmpty) return null;
    return tag.trim();
  }

  static Future<void> setPhaseTag(String? value) async {
    final prefs = await SharedPreferences.getInstance();
    if (value == null || value.trim().isEmpty) {
      await prefs.remove(_phaseTagKey);
    } else {
      await prefs.setString(_phaseTagKey, value.trim());
    }
  }
}
