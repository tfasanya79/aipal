import 'dart:async';
import 'dart:developer' as developer;
import 'dart:typed_data';

import 'package:open_wake_word/open_wake_word.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

import 'voice/microphone_manager.dart';
import 'voice/microphone_owner.dart';
import 'voice/voice_configuration.dart';

/// Shared OpenWakeWord pipeline for foreground and background isolates.
class WakeWordEngine {
  WakeWordEngine({
    required this.onWake,
    bool Function()? shouldSuppress,
    String modelVersion = '0.1',
    MicrophoneManager? microphoneManager,
  }) : _shouldSuppress = shouldSuppress,
       _modelVersion = modelVersion,
       _microphoneManager = microphoneManager ?? MicrophoneManager.instance;

  final void Function() onWake;
  bool Function()? _shouldSuppress;
  String _modelVersion;

  static const wakePhrase = 'Hi Pal';
  static const activationThreshold = VoiceConfiguration.wakeThresholdV1;
  static const activationThresholdV2 = VoiceConfiguration.wakeThresholdV2;
  static const _defaultWarmupMs = VoiceConfiguration.wakeWarmupMs;
  static String? lastInitError;

  /// Optional hook for agent debug logging (main isolate only).
  static void Function(
    String hypothesisId,
    String message,
    Map<String, dynamic> data,
  )?
  agentDebug;

  final MicrophoneManager _microphoneManager;
  StreamSubscription<Uint8List>? _audioSub;
  bool _initialized = false;
  bool _listening = false;
  bool _cooldown = false;
  bool _suppressed = false;
  int _pollCount = 0;
  double _maxProbSinceSample = 0;
  DateTime? _micStartedAt;
  double _effectiveThreshold = activationThreshold;

  bool get isListening => _listening;

  /// Set a per-user calibrated threshold (from wake enrollment prefs).
  void setCalibrationThreshold(double threshold) {
    _effectiveThreshold = threshold.clamp(0.005, 0.5);
  }

  void setShouldSuppress(bool Function()? fn) => _shouldSuppress = fn;

  void setSuppressed(bool value) => _suppressed = value;

  bool _isSuppressed() => _suppressed || (_shouldSuppress?.call() ?? false);

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
    // Try the configured model version first; if it's v0.2 and it fails
    // (e.g. incompatible ops in the on-device ONNX runtime build), fall
    // back to the known-working v0.1 model instead of leaving wake dead.
    final attemptOrder = _modelVersion == '0.2' ? ['0.2', '0.1'] : ['0.1'];
    for (final version in attemptOrder) {
      final ok = await _tryInitModel(version);
      if (ok) {
        _modelVersion = version;
        _initialized = true;
        if (version == '0.2') {
          if (_effectiveThreshold == activationThreshold) {
            _effectiveThreshold = activationThresholdV2;
          }
        } else if (_effectiveThreshold == activationThresholdV2) {
          _effectiveThreshold = activationThreshold;
        }
        developer.log(
          'WakeWordEngine initialized with model v$version',
          name: 'aipal.wake',
        );
        return true;
      }
      developer.log(
        'WakeWordEngine: model v$version failed to init ($lastInitError)'
        '${version == '0.2' ? ' — falling back to v0.1' : ''}',
        name: 'aipal.wake',
      );
    }
    return false;
  }

  /// Attempt to initialize OpenWakeWord with a specific model version.
  /// Returns true on success; sets [lastInitError] on failure.
  Future<bool> _tryInitModel(String version) async {
    try {
      final modelAssetPath = version == '0.2'
          ? 'assets/models/hi_pal_v0.2.onnx'
          : 'assets/models/hi_pal_v0.1.onnx';
      final ok = await OpenWakeWord.init(
        melModelAssetPath: 'assets/models/melspectrogram.onnx',
        embModelAssetPath: 'assets/models/embedding_model.onnx',
        wwModelAssetPaths: [modelAssetPath],
      );
      if (!ok) {
        final detail = OpenWakeWord.getLastError();
        lastInitError = detail.isNotEmpty
            ? 'OpenWakeWord.init failed (model v$version): $detail'
            : 'OpenWakeWord.init returned false (model v$version)';
        return false;
      }
      return true;
    } catch (e, st) {
      lastInitError = '${e.toString()} (model v$version)';
      developer.log(
        'WakeWordEngine init failed for v$version',
        name: 'aipal.wake',
        error: e,
        stackTrace: st,
      );
      return false;
    }
  }

  /// Switch to a different model version (0.1 or 0.2).
  /// If v0.2 is requested but unavailable, init() will transparently
  /// fall back to v0.1 and update [_modelVersion] accordingly.
  Future<bool> switchModelVersion(String version) async {
    if (_listening) {
      developer.log('Cannot switch model while listening', name: 'aipal.wake');
      return false;
    }

    _modelVersion = version;
    _initialized = false;
    return init();
  }

  /// The model version actually active after the most recent successful init
  /// (may differ from the requested version if a fallback occurred).
  String get activeModelVersion => _modelVersion;

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

    final acquired = await _microphoneManager.acquire(
      MicrophoneOwner.wakeWordEngine,
    );
    if (!acquired) {
      lastInitError =
          'Microphone is busy by ${_microphoneManager.currentOwnerLabel}';
      agentDebug?.call('H4', 'mic_busy', {
        'owner': _microphoneManager.currentOwnerLabel,
      });
      return;
    }

    Stream<Uint8List> stream;
    try {
      stream = await _microphoneManager.startStream(
        MicrophoneOwner.wakeWordEngine,
        const RecordConfig(
          encoder: AudioEncoder.pcm16bits,
          sampleRate: 16000,
          numChannels: 1,
        ),
      );
    } catch (e) {
      _microphoneManager.release(MicrophoneOwner.wakeWordEngine);
      lastInitError = 'Failed to start wake microphone stream: $e';
      return;
    }

    // Frame-driven (not timer-polled): activation is evaluated as each PCM
    // frame arrives from the mic stream, per the ChatGPT review's
    // recommendation to avoid a separate drifting Timer.periodic poll when
    // OpenWakeWord already streams frames.
    _audioSub = stream.listen(_onPcm);
    _listening = true;
    _pollCount = 0;
    _maxProbSinceSample = 0;
    _micStartedAt = DateTime.now();
    agentDebug?.call('H3', 'mic_stream_started', {
      'listening': true,
      'warmupMs': _defaultWarmupMs,
      'threshold': _effectiveThreshold,
    });
  }

  Future<void> stop() async {
    _listening = false;
    await _audioSub?.cancel();
    _audioSub = null;
    await _microphoneManager.stopRecording(MicrophoneOwner.wakeWordEngine);
    _microphoneManager.release(MicrophoneOwner.wakeWordEngine);
  }

  Future<void> dispose() async {
    await stop();
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
    _pollActivation();
  }

  bool _inWarmup() {
    final started = _micStartedAt;
    if (started == null) return false;
    return DateTime.now().difference(started).inMilliseconds < _defaultWarmupMs;
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
        'threshold': _effectiveThreshold,
        'activated': OpenWakeWord.isActivated(),
      });
      _maxProbSinceSample = prob;
    }
    if (OpenWakeWord.isActivated() || prob >= _effectiveThreshold) {
      _cooldown = true;
      agentDebug?.call('H3', 'wake_threshold_hit', {
        'prob': prob,
        'threshold': _effectiveThreshold,
      });
      onWake();
      Future.delayed(
        const Duration(seconds: VoiceConfiguration.wakeCooldownSeconds),
        () => _cooldown = false,
      );
    }
  }
}
