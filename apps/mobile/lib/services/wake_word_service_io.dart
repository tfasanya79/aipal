import 'package:flutter/foundation.dart';

import 'wake_word_engine.dart';

/// Foreground OpenWakeWord listener for "Hi Pal" (Android Companion + iOS).
class WakeWordService {
  WakeWordService({
    required this.onWake,
    this.shouldSuppress,
    this.calibratedThreshold,
  });

  final VoidCallback onWake;
  final bool Function()? shouldSuppress;
  final double? calibratedThreshold;

  WakeWordEngine? _engine;

  bool get isListening => _engine?.isListening ?? false;
  String get phrase => WakeWordEngine.wakePhrase;

  WakeWordEngine _getEngine() {
    _engine ??= WakeWordEngine(onWake: onWake, shouldSuppress: shouldSuppress);
    if (calibratedThreshold != null) {
      _engine!.setCalibrationThreshold(calibratedThreshold!);
    }
    return _engine!;
  }

  Future<bool> ensureMicPermission() async => _getEngine().ensureMicPermission();

  Future<bool> init() async => _getEngine().init();

  Future<void> start() async => _getEngine().start();

  Future<void> stop() async {
    await _engine?.stop();
  }

  Future<void> dispose() async {
    await _engine?.dispose();
    _engine = null;
  }
}
