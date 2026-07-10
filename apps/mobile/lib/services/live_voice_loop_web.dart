import 'dart:async';

import 'package:http/http.dart' as http;
import 'package:record/record.dart';

import 'voice/microphone_manager.dart';
import 'voice/microphone_owner.dart';
import 'voice/voice_configuration.dart';

/// Browser Live listening with VAD (same UX as native; uses MediaRecorder via record_web).
class LiveVoiceLoop {
  LiveVoiceLoop({
    required this.onSegment,
    this.onSegmentRejected,
    this.onSpeechStart,
    this.shouldSuppress,
    this.isSpeakingForVad,
    this.silenceMs = 800,
    this.maxSegmentMs = VoiceConfiguration.vadMaxSegmentMs,
    this.thresholdDb = VoiceConfiguration.vadThresholdDbWeb,
    this.thresholdDbSpeaking = VoiceConfiguration.vadThresholdDbSpeakingWeb,
    MicrophoneManager? microphoneManager,
  }) : _microphoneManager = microphoneManager ?? MicrophoneManager.instance;

  final Future<void> Function(List<int> bytes) onSegment;
  final void Function()? onSegmentRejected;
  final void Function()? onSpeechStart;
  final bool Function()? shouldSuppress;
  final bool Function()? isSpeakingForVad;
  final int silenceMs;
  final int maxSegmentMs;
  final double thresholdDb;
  final double thresholdDbSpeaking;

  static const _tickMs = VoiceConfiguration.vadTickMs;

  final MicrophoneManager _microphoneManager;
  Timer? _ticker;
  bool _active = false;
  bool _inSegment = false;
  int _silenceAccumMs = 0;
  int _segmentStartedAt = 0;
  int _dynamicSilenceMs = 800;
  String? _currentPath;
  bool _processingSegment = false;

  bool get isActive => _active;

  Future<bool> ensureMicPermission() async {
    return _recorderHasPermission();
  }

  Future<bool> _recorderHasPermission() async {
    // record_web supports hasPermission() without needing an owned recorder.
    return AudioRecorder().hasPermission();
  }

  Future<void> start() async {
    if (_active) return;
    if (!await ensureMicPermission()) {
      throw StateError(
        'Microphone permission denied — allow mic in browser settings',
      );
    }
    final acquired = await _microphoneManager.acquire(
      MicrophoneOwner.liveVoiceLoop,
    );
    if (!acquired) {
      throw StateError(
        'Microphone is busy by ${_microphoneManager.currentOwnerLabel}',
      );
    }
    _active = true;
    _dynamicSilenceMs = silenceMs;
    await _startRecording();
    _ticker = Timer.periodic(const Duration(milliseconds: _tickMs), (_) {
      unawaited(_tick());
    });
  }

  Future<void> stop() async {
    _active = false;
    _ticker?.cancel();
    _ticker = null;
    await _microphoneManager.stopRecording(MicrophoneOwner.liveVoiceLoop);
    _inSegment = false;
    _currentPath = null;
    _microphoneManager.release(MicrophoneOwner.liveVoiceLoop);
  }

  Future<void> dispose() async {
    await stop();
  }

  RecordConfig get _config {
    return const RecordConfig(
      encoder: AudioEncoder.opus,
      bitRate: 128000,
      sampleRate: 48000,
    );
  }

  Future<void> _startRecording() async {
    if (!_active) return;
    if (shouldSuppress?.call() ?? false) return;
    if (await _microphoneManager.isRecording()) return;
    _currentPath = 'aipal-live-${DateTime.now().millisecondsSinceEpoch}.webm';
    await _microphoneManager.start(
      MicrophoneOwner.liveVoiceLoop,
      _config,
      path: _currentPath!,
    );
    _segmentStartedAt = DateTime.now().millisecondsSinceEpoch;
    _silenceAccumMs = 0;
    _inSegment = false;
  }

  Future<void> _tick() async {
    if (!_active || _processingSegment) return;

    if (shouldSuppress?.call() ?? false) {
      _silenceAccumMs = 0;
      _inSegment = false;
      if (await _microphoneManager.isRecording()) {
        await _microphoneManager.stopRecording(MicrophoneOwner.liveVoiceLoop);
      }
      return;
    }

    if (!await _microphoneManager.isRecording()) {
      await _startRecording();
      if (!await _microphoneManager.isRecording()) return;
    }

    final amp = await _microphoneManager.getAmplitude();
    final threshold = (isSpeakingForVad?.call() ?? false)
        ? thresholdDbSpeaking
        : thresholdDb;
    final speaking = amp.current > threshold;

    if (speaking) {
      _silenceAccumMs = 0;
      if (!_inSegment) {
        _inSegment = true;
        _segmentStartedAt = DateTime.now().millisecondsSinceEpoch;
        onSpeechStart?.call();
      }
    } else if (_inSegment) {
      _silenceAccumMs += _tickMs;
    }

    if (_inSegment) {
      final elapsed = DateTime.now().millisecondsSinceEpoch - _segmentStartedAt;
      if (_silenceAccumMs >= _dynamicSilenceMs || elapsed >= maxSegmentMs) {
        await _endSegment();
      }
    }
  }

  Future<void> _endSegment() async {
    if (!_inSegment || _processingSegment) return;
    _processingSegment = true;
    _inSegment = false;
    _silenceAccumMs = 0;

    String? blobUrl;
    if (await _microphoneManager.isRecording()) {
      blobUrl = await _microphoneManager.stopRecording(
        MicrophoneOwner.liveVoiceLoop,
      );
    }
    _currentPath = null;

    final elapsed = DateTime.now().millisecondsSinceEpoch - _segmentStartedAt;
    _dynamicSilenceMs = (elapsed * 0.25).round().clamp(700, 1700);

    if (blobUrl != null && blobUrl.isNotEmpty) {
      try {
        final bytes = await _readBlobUrl(blobUrl);
        if (bytes.length >= 64) {
          await onSegment(bytes);
        }
      } catch (_) {}
    }

    _processingSegment = false;
    if (_active && !(shouldSuppress?.call() ?? false)) {
      await _startRecording();
    }
  }

  Future<List<int>> _readBlobUrl(String url) async {
    final response = await http.get(Uri.parse(url));
    return response.bodyBytes;
  }
}
