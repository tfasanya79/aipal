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
  static const activationThreshold = 0.28;

  /// Last init failure message (for FGS → main isolate reporting).
  static String? lastInitError;

  /// Optional hook for agent debug logging (main isolate only).
  static void Function(
    String hypothesisId,
    String message,
    Map<String, dynamic> data,
  )? agentDebug;

  final AudioRecorder _recorder = AudioRecorder();
  StreamSubscription<Uint8List>? _audioSub;
  Timer? _pollTimer;
  bool _initialized = false;
  bool _listening = false;
  bool _cooldown = false;
  bool _suppressed = false;
  int _pollCount = 0;
  double _maxProbSinceSample = 0;
  DateTime? _micStartedAt;
  static const _warmupMs = 3000;

  bool get isListening => _listening;

  void setShouldSuppress(bool Function()? fn) => _shouldSuppress = fn;

  void setSuppressed(bool value) => _suppressed = value;

  bool _isSuppressed() =>
      _suppressed || (_shouldSuppress?.call() ?? false);

  Future<bool> ensureMicPermission() async {
    final status = await Permission.microphone.request();
    return status.isGranted;
  }

  Future<bool>? _initFuture;
  Future<void>? _startFuture;

  Future<bool> init() async {
    if (_initialized) return true;
    if (_initFuture != null) return _initFuture!;
    _initFuture = _initImpl();
    try {
      return await _initFuture!;
    } finally {
      _initFuture = null;
    }
  }

  Future<bool> _initImpl() async {
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
    if (_startFuture != null) return _startFuture!;
    _startFuture = _startImpl();
    try {
      await _startFuture!;
    } finally {
      _startFuture = null;
    }
  }

  Future<void> _startImpl() async {
    if (_listening) return;
    if (!_initialized && !await init()) return;
    if (_isSuppressed()) {
      lastInitError = 'Wake suppressed';
      agentDebug?.call('H4', 'start_suppressed', {'suppressed': true});
      return;
    }
    if (!await ensureMicPermission()) {
      lastInitError = 'Microphone permission denied';
      agentDebug?.call('H4', 'mic_denied', {});
      return;
    }

    final stream = await _recorder.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
    ));

    _audioSub = stream.listen(_onPcm);
    _pollTimer ??=
        Timer.periodic(const Duration(milliseconds: pollMs), (_) => _pollActivation());
    _listening = true;
    _pollCount = 0;
    _maxProbSinceSample = 0;
    _micStartedAt = DateTime.now();
    agentDebug?.call('H3', 'mic_stream_started', {'listening': true, 'warmupMs': _warmupMs});
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

  bool _inWarmup() {
    final started = _micStartedAt;
    if (started == null) return false;
    return DateTime.now().difference(started).inMilliseconds < _warmupMs;
  }

  void _pollActivation() {
    if (!_listening || _cooldown || _isSuppressed()) return;
    if (_inWarmup()) return;
    final prob = OpenWakeWord.getProbability();
    if (prob > _maxProbSinceSample) _maxProbSinceSample = prob;
    _pollCount++;
    if (_pollCount % 50 == 0) {
      agentDebug?.call('H3', 'wake_prob_sample', {
        'prob': prob,
        'maxProb': _maxProbSinceSample,
        'threshold': activationThreshold,
        'activated': OpenWakeWord.isActivated(),
      });
      _maxProbSinceSample = prob;
    }
    if (OpenWakeWord.isActivated() || prob >= activationThreshold) {
      _cooldown = true;
      agentDebug?.call('H3', 'wake_threshold_hit', {'prob': prob});
      onWake();
      Future.delayed(const Duration(seconds: 2), () => _cooldown = false);
    }
  }
}
