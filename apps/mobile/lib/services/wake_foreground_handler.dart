import 'dart:async';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import 'wake_word_engine.dart';

/// Foreground-task isolate handler for Android background "Hi Pal" listening.
class WakeForegroundHandler extends TaskHandler {
  WakeWordEngine? _engine;

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    _engine = WakeWordEngine(onWake: _onWakeDetected);
    if (!await _engine!.init()) {
      FlutterForegroundTask.sendDataToMain({
        'event': 'engine_failed',
        'error': WakeWordEngine.lastInitError ?? 'OpenWakeWord init failed',
      });
      return;
    }
    await _engine!.start();
    if (!_engine!.isListening) {
      FlutterForegroundTask.sendDataToMain({
        'event': 'engine_failed',
        'error': WakeWordEngine.lastInitError ?? 'Wake engine failed to start listener',
      });
    } else {
      FlutterForegroundTask.sendDataToMain({
        'event': 'engine_ready',
        'modelVersion': _engine!.activeModelVersion,
      });
    }
  }

  @override
  void onRepeatEvent(DateTime timestamp) {}

  @override
  Future<void> onDestroy(DateTime timestamp) async {
    await _engine?.dispose();
    _engine = null;
  }

  @override
  void onReceiveData(Object data) {
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
      unawaited(engine.stop());
    } else {
      unawaited(_startEngine(engine));
    }
  }

  Future<void> _startEngine(WakeWordEngine engine) async {
    await engine.start();
    if (!engine.isListening) {
      FlutterForegroundTask.sendDataToMain({
        'event': 'engine_failed',
        'error': WakeWordEngine.lastInitError ?? 'Wake engine failed to restart mic',
      });
    } else {
      FlutterForegroundTask.sendDataToMain({
        'event': 'engine_ready',
        'modelVersion': engine.activeModelVersion,
      });
    }
  }

  void _onWakeDetected() {
    FlutterForegroundTask.sendDataToMain({'event': 'wake'});
    FlutterForegroundTask.launchApp();
  }
}

@pragma('vm:entry-point')
void startWakeCallback() {
  FlutterForegroundTask.setTaskHandler(WakeForegroundHandler());
}
