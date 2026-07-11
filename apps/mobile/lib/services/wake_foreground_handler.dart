import 'dart:async';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import 'wake_word_engine.dart';

/// Foreground-task isolate handler for Android background "Hi Pal" listening.
///
/// Round 8 root-cause fix: every entry point below is wrapped in try/catch.
/// This isolate has no top-level error handler of its own (unlike the main
/// isolate, which installs PlatformDispatcher.instance.onError in
/// main.dart) -- before this fix, any uncaught exception here (e.g. a
/// permission-channel issue specific to this isolate, or a native init
/// failure) silently killed the isolate: no engine_ready/engine_failed
/// message was ever sent, which is why the main isolate always timed out
/// after 8s with a generic "did not start" error, and why the Android
/// foreground service process could crash/relaunch repeatedly with no
/// diagnosable cause. Now every failure path is guaranteed to report a
/// real error message back instead of dying silently.
class WakeForegroundHandler extends TaskHandler {
  WakeWordEngine? _engine;

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    try {
      // canRequestPermission: false -- this isolate has no Activity;
      // see WakeWordEngine's _canRequestPermission doc for why .request()
      // would crash here. Permission must already be granted by the main
      // isolate before this isolate is ever started.
      _engine = WakeWordEngine(
        onWake: _onWakeDetected,
        canRequestPermission: false,
      );
      if (!await _engine!.init()) {
        _reportFailure(
          WakeWordEngine.lastInitError ?? 'OpenWakeWord init failed',
        );
        return;
      }
      await _engine!.start();
      if (!_engine!.isListening) {
        _reportFailure(
          WakeWordEngine.lastInitError ?? 'Wake engine failed to start listener',
        );
      } else {
        _reportReady();
      }
    } catch (e, st) {
      _reportFailure('onStart crashed: $e', stackTrace: st);
    }
  }

  @override
  void onRepeatEvent(DateTime timestamp) {}

  @override
  Future<void> onDestroy(DateTime timestamp) async {
    try {
      await _engine?.dispose();
    } catch (_) {
      // Best-effort cleanup; nothing to report to a shutting-down isolate.
    }
    _engine = null;
  }

  @override
  void onReceiveData(Object data) {
    try {
      if (data is! Map) return;
      final engine = _engine;
      if (engine == null) return;
      if (data['ensure_listening'] == true) {
        engine.setSuppressed(false);
        unawaited(_startEngine(engine));
        return;
      }
      if (!data.containsKey('suppress')) return;
      final suppress = data['suppress'] == true;
      engine.setSuppressed(suppress);
      if (suppress) {
        unawaited(_guardedStop(engine));
      } else {
        unawaited(_startEngine(engine));
      }
    } catch (e, st) {
      _reportFailure('onReceiveData crashed: $e', stackTrace: st);
    }
  }

  Future<void> _guardedStop(WakeWordEngine engine) async {
    try {
      await engine.stop();
    } catch (e, st) {
      _reportFailure('stop crashed: $e', stackTrace: st);
    }
  }

  Future<void> _startEngine(WakeWordEngine engine) async {
    try {
      await engine.start();
      if (!engine.isListening) {
        _reportFailure(
          WakeWordEngine.lastInitError ?? 'Wake engine failed to restart mic',
        );
      } else {
        _reportReady(engine: engine);
      }
    } catch (e, st) {
      _reportFailure('_startEngine crashed: $e', stackTrace: st);
    }
  }

  void _reportReady({WakeWordEngine? engine}) {
    try {
      FlutterForegroundTask.sendDataToMain({
        'event': 'engine_ready',
        'modelVersion': (engine ?? _engine)?.activeModelVersion,
      });
    } catch (_) {
      // If even sendDataToMain throws, there's nothing further we can do.
    }
  }

  void _reportFailure(String error, {StackTrace? stackTrace}) {
    try {
      FlutterForegroundTask.sendDataToMain({
        'event': 'engine_failed',
        'error': error,
      });
    } catch (_) {
      // If even sendDataToMain throws, there's nothing further we can do.
    }
  }

  void _onWakeDetected() {
    try {
      FlutterForegroundTask.sendDataToMain({'event': 'wake'});
      FlutterForegroundTask.launchApp();
    } catch (_) {
      // Best-effort; a failure here shouldn't crash the isolate either.
    }
  }
}

@pragma('vm:entry-point')
void startWakeCallback() {
  FlutterForegroundTask.setTaskHandler(WakeForegroundHandler());
}
