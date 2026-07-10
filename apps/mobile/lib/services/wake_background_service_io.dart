import 'dart:io' show Platform;

import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:permission_handler/permission_handler.dart';

import 'voice/voice_configuration.dart';
import 'wake_foreground_handler.dart';

/// Android foreground microphone service for background "Hi Pal" wake (C2).
class WakeBackgroundService {
  static const _serviceId = 258;

  static Future<void> init() async {
    if (!Platform.isAndroid) return;
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'aipal_wake',
        channelName: 'Hi Pal wake word',
        channelDescription:
            'AiPal listens for Hi Pal when enabled in Settings.',
        onlyAlertOnce: true,
        channelImportance: NotificationChannelImportance.LOW,
        priority: NotificationPriority.LOW,
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: false,
        playSound: false,
      ),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.nothing(),
        autoRunOnBoot: false,
        autoRunOnMyPackageReplaced: false,
        allowWakeLock: true,
      ),
    );
  }

  static Future<bool> _ensureNotificationPermission() async {
    final status = await FlutterForegroundTask.checkNotificationPermission();
    if (status == NotificationPermission.granted) return true;
    final requested =
        await FlutterForegroundTask.requestNotificationPermission();
    return requested == NotificationPermission.granted;
  }

  /// Ensures the wake foreground service is running.
  ///
  /// [forceRestart] must be true whenever the caller knows a previous
  /// listener attempt failed (e.g. "Retry listener" tap, or a timed-out
  /// engine_ready wait). `FlutterForegroundTask.isRunningService` only
  /// reports whether the Android service process is alive, NOT whether the
  /// isolate/engine inside it is actually initialized and listening. A
  /// service can be stuck "running" with a dead/uninitialized engine after a
  /// native init failure or app-update edge case, and blindly trusting that
  /// flag turns every retry into a silent no-op (message sent to a broken
  /// isolate that never replies). When [forceRestart] is true we always stop
  /// then start fresh, never short-circuiting on the stale "already running"
  /// state.
  /// Pure decision logic extracted from [ensureRunning] so the exact Bug #2
  /// fix (never trust a stale "already running" flag when the caller knows
  /// the previous attempt failed) can be unit tested without touching any
  /// platform channel.
  ///
  /// Returns true when it is safe to short-circuit and report success
  /// without touching the service at all.
  static bool shouldTrustAlreadyRunning({
    required bool alreadyRunning,
    required bool forceRestart,
  }) => alreadyRunning && !forceRestart;

  /// Returns true when the existing (stuck/possibly-dead) service instance
  /// must be stopped before starting a fresh one.
  static bool shouldStopBeforeRestart({
    required bool alreadyRunning,
    required bool forceRestart,
  }) => alreadyRunning && forceRestart;

  static Future<bool> ensureRunning({bool forceRestart = false}) async {
    if (!Platform.isAndroid) return false;
    final mic = await Permission.microphone.request();
    if (!mic.isGranted) return false;
    if (!await _ensureNotificationPermission()) return false;

    final alreadyRunning = await FlutterForegroundTask.isRunningService;
    if (shouldTrustAlreadyRunning(
      alreadyRunning: alreadyRunning,
      forceRestart: forceRestart,
    )) {
      return true;
    }

    if (shouldStopBeforeRestart(
      alreadyRunning: alreadyRunning,
      forceRestart: forceRestart,
    )) {
      await FlutterForegroundTask.stopService();
      await Future.delayed(VoiceConfiguration.wakeServiceRestartSettleDelay);
    }

    final result = await FlutterForegroundTask.startService(
      serviceId: _serviceId,
      notificationTitle: 'AiPal is listening for Hi Pal',
      notificationText: 'Say Hi Pal to start Live hands-free',
      callback: startWakeCallback,
    );
    return result is ServiceRequestSuccess;
  }

  static Future<void> stop() async {
    if (!Platform.isAndroid) return;
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
  }

  static void setSuppressed(bool suppressed) {
    if (!Platform.isAndroid) return;
    FlutterForegroundTask.sendDataToTask({'suppress': suppressed});
  }

  /// Ask the FGS isolate to (re)start the mic pipeline when Resting with wake enabled.
  static void ensureListening() {
    if (!Platform.isAndroid) return;
    FlutterForegroundTask.sendDataToTask({'ensure_listening': true});
  }

  static Future<bool> isRunning() async {
    if (!Platform.isAndroid) return false;
    return FlutterForegroundTask.isRunningService;
  }
}
