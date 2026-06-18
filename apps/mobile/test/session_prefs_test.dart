import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:aipal/services/session_prefs.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
  });

  test('session recording defaults to enabled', () async {
    expect(await SessionPrefs.isRecordingEnabled(), isTrue);
  });

  test('session recording can be disabled', () async {
    await SessionPrefs.setRecordingEnabled(false);
    expect(await SessionPrefs.isRecordingEnabled(), isFalse);
  });

  test('phase tag round trip', () async {
    await SessionPrefs.setPhaseTag('build-39');
    expect(await SessionPrefs.phaseTag(), 'build-39');
    await SessionPrefs.setPhaseTag('');
    expect(await SessionPrefs.phaseTag(), isNull);
  });
}
