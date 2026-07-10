import 'package:aipal/services/wake_background_service_io.dart';
import 'package:flutter_test/flutter_test.dart';

/// Round 7 regression tests for Bug #2 ("Retry listener" never actually
/// recovers). `FlutterForegroundTask.isRunningService` only reports whether
/// the Android service process is alive, NOT whether the isolate/engine
/// inside it is actually initialized and listening. Before this fix, every
/// retry (manual "Retry listener" tap or the bounded auto-retry) trusted
/// that flag and simply re-sent a message to a possibly-dead isolate --
/// a guaranteed no-op whenever the service was stuck. These tests pin down
/// the exact decision logic of the fix without touching any platform
/// channel.
void main() {
  group('WakeBackgroundService.shouldTrustAlreadyRunning', () {
    test('trusts a running service when no restart was requested', () {
      expect(
        WakeBackgroundService.shouldTrustAlreadyRunning(
          alreadyRunning: true,
          forceRestart: false,
        ),
        isTrue,
      );
    });

    test(
      'Bug #2 fix: does NOT trust a running service when forceRestart is '
      'true, even though the previous (buggy) behavior always trusted it',
      () {
        expect(
          WakeBackgroundService.shouldTrustAlreadyRunning(
            alreadyRunning: true,
            forceRestart: true,
          ),
          isFalse,
        );
      },
    );

    test('never trusts a service that is not running', () {
      expect(
        WakeBackgroundService.shouldTrustAlreadyRunning(
          alreadyRunning: false,
          forceRestart: false,
        ),
        isFalse,
      );
      expect(
        WakeBackgroundService.shouldTrustAlreadyRunning(
          alreadyRunning: false,
          forceRestart: true,
        ),
        isFalse,
      );
    });
  });

  group('WakeBackgroundService.shouldStopBeforeRestart', () {
    test('Bug #2 fix: stops the stuck service before starting fresh when '
        'forceRestart is requested on an already-running service', () {
      expect(
        WakeBackgroundService.shouldStopBeforeRestart(
          alreadyRunning: true,
          forceRestart: true,
        ),
        isTrue,
      );
    });

    test('does not stop a healthy service when no restart was requested', () {
      expect(
        WakeBackgroundService.shouldStopBeforeRestart(
          alreadyRunning: true,
          forceRestart: false,
        ),
        isFalse,
      );
    });

    test('does not attempt to stop a service that is not running', () {
      expect(
        WakeBackgroundService.shouldStopBeforeRestart(
          alreadyRunning: false,
          forceRestart: true,
        ),
        isFalse,
      );
      expect(
        WakeBackgroundService.shouldStopBeforeRestart(
          alreadyRunning: false,
          forceRestart: false,
        ),
        isFalse,
      );
    });
  });
}
