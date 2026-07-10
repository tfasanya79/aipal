import 'dart:async';
import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

import 'voice/microphone_manager.dart';
import 'voice/microphone_owner.dart';
import 'voice/voice_configuration.dart';

/// Continuous Live listening with voice-activity segmentation (ported from MVP VAD).
class LiveVoiceLoop {
  LiveVoiceLoop({
    required this.onSegment,
    this.onSegmentRejected,
    this.onSpeechStart,
    this.shouldSuppress,
    this.isSpeakingForVad,
    this.silenceMs = VoiceConfiguration.vadSilenceMs,
    this.maxSegmentMs = VoiceConfiguration.vadMaxSegmentMs,
    this.minVoicedMs = 450,
    this.minUploadBytes = 1024,
    this.thresholdDb = VoiceConfiguration.vadThresholdDbIo,
    this.thresholdDbSpeaking = VoiceConfiguration.vadThresholdDbSpeakingIo,
    MicrophoneManager? microphoneManager,
  }) : _microphoneManager = microphoneManager ?? MicrophoneManager.instance;

  final Future<void> Function(List<int> bytes) onSegment;
  final void Function()? onSegmentRejected;
  final void Function()? onSpeechStart;
  final bool Function()? shouldSuppress;
  final bool Function()? isSpeakingForVad;
  final int silenceMs;
  final int maxSegmentMs;
  final int minVoicedMs;
  final int minUploadBytes;
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
  int _voicedMs = 0;

  bool get isActive => _active;

  Future<bool> ensureMicPermission() async {
    final status = await Permission.microphone.request();
    return status.isGranted;
  }

  Future<void> start() async {
    if (_active) return;
    if (!await ensureMicPermission()) {
      throw StateError('Microphone permission denied');
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

  Future<void> _startRecording() async {
    if (!_active) return;
    if (shouldSuppress?.call() ?? false) return;
    if (await _microphoneManager.isRecording()) return;
    final dir = await getTemporaryDirectory();
    _currentPath =
        '${dir.path}/aipal-live-${DateTime.now().millisecondsSinceEpoch}.m4a';
    await _microphoneManager.start(
      MicrophoneOwner.liveVoiceLoop,
      const RecordConfig(
        encoder: AudioEncoder.aacLc,
        bitRate: 128000,
        sampleRate: 44100,
      ),
      path: _currentPath!,
    );
    _segmentStartedAt = DateTime.now().millisecondsSinceEpoch;
    _silenceAccumMs = 0;
    _inSegment = false;
    _voicedMs = 0;
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
      _voicedMs += _tickMs;
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

    final path = _currentPath;
    String? finishedPath;
    if (await _microphoneManager.isRecording()) {
      finishedPath = await _microphoneManager.stopRecording(
        MicrophoneOwner.liveVoiceLoop,
      );
    }
    finishedPath ??= path;
    _currentPath = null;

    final elapsed = DateTime.now().millisecondsSinceEpoch - _segmentStartedAt;
    _dynamicSilenceMs = (elapsed * 0.25).round().clamp(700, 1700);

    if (finishedPath != null) {
      final file = File(finishedPath);
      if (await file.exists()) {
        final size = await file.length();
        if (size >= minUploadBytes && _voicedMs >= minVoicedMs) {
          await onSegment(await file.readAsBytes());
        } else {
          try {
            await file.delete();
          } catch (_) {}
          onSegmentRejected?.call();
        }
      }
    }

    _voicedMs = 0;
    _processingSegment = false;
    if (_active && !(shouldSuppress?.call() ?? false)) {
      await _startRecording();
    }
  }
}
