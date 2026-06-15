import 'dart:async';
import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

/// Continuous Live listening with voice-activity segmentation (ported from MVP VAD).
class LiveVoiceLoop {
  LiveVoiceLoop({
    required this.onSegment,
    this.onSpeechStart,
    this.shouldSuppress,
    this.silenceMs = 1200,
    this.maxSegmentMs = 10000,
    this.thresholdDb = -35.0,
  });

  final Future<void> Function(List<int> bytes) onSegment;
  final void Function()? onSpeechStart;
  final bool Function()? shouldSuppress;
  final int silenceMs;
  final int maxSegmentMs;
  final double thresholdDb;

  static const _tickMs = 120;

  final AudioRecorder _recorder = AudioRecorder();
  Timer? _ticker;
  bool _active = false;
  bool _inSegment = false;
  int _silenceAccumMs = 0;
  int _segmentStartedAt = 0;
  int _dynamicSilenceMs = 1200;
  String? _currentPath;
  bool _processingSegment = false;

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
    if (await _recorder.isRecording()) {
      await _recorder.stop();
    }
    _inSegment = false;
    _currentPath = null;
  }

  Future<void> dispose() async {
    await stop();
    await _recorder.dispose();
  }

  Future<void> _startRecording() async {
    if (!_active) return;
    if (shouldSuppress?.call() ?? false) return;
    if (await _recorder.isRecording()) return;
    final dir = await getTemporaryDirectory();
    _currentPath = '${dir.path}/aipal-live-${DateTime.now().millisecondsSinceEpoch}.m4a';
    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.aacLc, bitRate: 128000, sampleRate: 44100),
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
      if (await _recorder.isRecording()) {
        await _recorder.stop();
      }
      return;
    }

    if (!await _recorder.isRecording()) {
      await _startRecording();
      if (!await _recorder.isRecording()) return;
    }

    final amp = await _recorder.getAmplitude();
    final speaking = amp.current > thresholdDb;

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

    final path = _currentPath;
    String? finishedPath;
    if (await _recorder.isRecording()) {
      finishedPath = await _recorder.stop();
    }
    finishedPath ??= path;
    _currentPath = null;

    final elapsed = DateTime.now().millisecondsSinceEpoch - _segmentStartedAt;
    _dynamicSilenceMs = (elapsed * 0.25).round().clamp(950, 1700);

    if (finishedPath != null) {
      final file = File(finishedPath);
      if (await file.exists()) {
        final size = await file.length();
        if (size >= 64) {
          await onSegment(await file.readAsBytes());
        } else {
          try {
            await file.delete();
          } catch (_) {}
        }
      }
    }

    _processingSegment = false;
    if (_active && !(shouldSuppress?.call() ?? false)) {
      await _startRecording();
    }
  }
}
