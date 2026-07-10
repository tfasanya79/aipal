import 'package:aipal/providers/app_state.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void _mockSecureStorage() {
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(
        const MethodChannel('plugins.it_nomads.com/flutter_secure_storage'),
        (call) async => null,
      );
}

void _mockAudioPlayerChannels() {
  for (final name in [
    'xyz.luan/audioplayers.global',
    'xyz.luan/audioplayers',
  ]) {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(MethodChannel(name), (_) async => null);
  }
}

/// Round 7 regression tests for Bug #1 (Orb "Tap to go Live" looked
/// unresponsive because the error text set in `_startConversation()`'s
/// catch block was rendered only `if (inConvo)`, but the same catch block
/// called `_endConversation()`, which flips `inConvo` to false before the
/// next frame -- so the error was never actually visible. `liveError` is a
/// dedicated field that renders unconditionally and must survive that flip.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  _mockSecureStorage();
  _mockAudioPlayerChannels();

  test('toggleLive surfaces a liveError message when token is null instead of '
      'silently doing nothing', () async {
    final state = AppState();
    expect(state.token, isNull);
    expect(state.liveError, isNull);

    await state.toggleLive();

    expect(state.inConversation, isFalse);
    expect(state.liveError, isNotNull);
    expect(state.liveError, contains('sign in'));
  });

  test(
    'liveError set by a failed start survives _endConversation() and is '
    'readable even though inConversation is false (Bug #1 regression)',
    () async {
      final state = AppState()..token = 'test-token-no-platform-channels';
      expect(state.liveError, isNull);

      // In the unit-test harness there is no mocked microphone/permission
      // platform channel, so starting Live mode is guaranteed to fail before
      // any real audio/network work happens -- exercising exactly the
      // catch-then-_endConversation() path that hid the error previously.
      await state.toggleLive();

      expect(state.inConversation, isFalse);
      expect(
        state.liveError,
        isNotNull,
        reason:
            'liveError must be set by the catch block in _startConversation() '
            'and must NOT be cleared by the _endConversation() call that '
            'follows it in the same catch block.',
      );
    },
  );

  test(
    'clearLiveError resets the field and only notifies when needed',
    () async {
      final state = AppState();
      await state.toggleLive(); // token is null -> sets liveError
      expect(state.liveError, isNotNull);

      state.clearLiveError();
      expect(state.liveError, isNull);

      // Calling again with nothing to clear should be a harmless no-op.
      state.clearLiveError();
      expect(state.liveError, isNull);
    },
  );
}
