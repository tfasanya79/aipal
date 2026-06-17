import 'dart:async';
import 'dart:developer' as developer;
import 'dart:typed_data';

import 'package:open_wake_word/open_wake_word.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

/// Shared OpenWakeWord pipeline for foreground and background isolates.
class WakeWordEngine {
  WakeWordEngine({
    required this.onWake,
    bool Function()? shouldSuppress,
  }) : _shouldSuppress = shouldSuppress;

  final void Function() onWake;
  bool Function()? _shouldSuppress;

  static const wakePhrase = 'Hi Pal';
  static const pollMs = 100;
  static const activationThreshold = 0.5;

  /// Last init failure message (for FGS → main isolate reporting).
  static String? lastInitError;

  final AudioRecorder _recorder = AudioRecorder();
  StreamSubscription<Uint8List>? _audioSub;
  Timer? _pollTimer;
  bool _initialized = false;
  bool _listening = false;
  bool _cooldown = false;
  bool _suppressed = false;

  bool get isListening => _listening;

  void setShouldSuppress(bool Function()? fn) => _shouldSuppress = fn;

  void setSuppressed(bool value) => _suppressed = value;

  bool _isSuppressed() =>
      _suppressed || (_shouldSuppress?.call() ?? false);

  Future<bool> ensureMicPermission() async {
    final status = await Permission.microphone.request();
    return status.isGranted;
  }

  Future<bool> init() async {
    if (_initialized) return true;
    lastInitError = null;
    try {
      final ok = await OpenWakeWord.init(
        melModelAssetPath: 'assets/models/melspectrogram.onnx',
        embModelAssetPath: 'assets/models/embedding_model.onnx',
        wwModelAssetPaths: const ['assets/models/hi_pal_v0.1.onnx'],
      );
      if (!ok) {
        lastInitError = 'OpenWakeWord.init returned false';
        developer.log('WakeWordEngine: $lastInitError', name: 'aipal.wake');
        return false;
      }
      _initialized = true;
      return true;
    } catch (e, st) {
      lastInitError = e.toString();
      developer.log('WakeWordEngine init failed', name: 'aipal.wake', error: e, stackTrace: st);
      return false;
    }
  }

  Future<void> start() async {
    if (_listening) return;
    if (!_initialized && !await init()) return;
    if (_isSuppressed()) return;
    if (!await ensureMicPermission()) return;

    final stream = await _recorder.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
    ));

    _audioSub = stream.listen(_onPcm);
    _pollTimer ??=
        Timer.periodic(const Duration(milliseconds: pollMs), (_) => _pollActivation());
    _listening = true;
  }

  Future<void> stop() async {
    _listening = false;
    await _audioSub?.cancel();
    _audioSub = null;
    if (await _recorder.isRecording()) {
      await _recorder.stop();
    }
  }

  Future<void> dispose() async {
    _pollTimer?.cancel();
    _pollTimer = null;
    await stop();
    await _recorder.dispose();
    if (_initialized) {
      OpenWakeWord.destroy();
      _initialized = false;
    }
  }

  void _onPcm(Uint8List bytes) {
    if (!_listening || _isSuppressed()) return;
    final int16 = Int16List(bytes.length ~/ 2);
    for (var i = 0; i < int16.length; i++) {
      var sample = (bytes[i * 2] & 0xff) | ((bytes[i * 2 + 1] & 0xff) << 8);
      if (sample >= 0x8000) sample -= 0x10000;
      int16[i] = sample;
    }
    OpenWakeWord.processAudio(int16);
  }

  void _pollActivation() {
    if (!_listening || _cooldown || _isSuppressed()) return;
    final prob = OpenWakeWord.getProbability();
    if (OpenWakeWord.isActivated() || prob >= activationThreshold) {
      _cooldown = true;
      onWake();
      Future.delayed(const Duration(seconds: 2), () => _cooldown = false);
    }
  }
}
