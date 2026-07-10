import 'dart:async';
import 'dart:typed_data';

import 'package:record/record.dart';

import 'microphone_owner.dart';

/// Single owner of the app's microphone hardware access.
///
/// Per the ChatGPT architecture review (item #3): "Only one object should
/// ever open or close the microphone." Previously this class was only a
/// lock/token -- each service (wake engine, live voice loop) still created
/// and drove its own `AudioRecorder`. Now `MicrophoneManager` owns the single
/// shared `AudioRecorder` instance; callers must hold ownership (via
/// [acquire]) before they can start/stop/read from it.
class MicrophoneManager {
  MicrophoneManager._();

  static final MicrophoneManager instance = MicrophoneManager._();

  // Lazily created so acquire/release ownership logic (exercised in
  // pure-Dart unit tests) never touches the record plugin's platform
  // channel unless a caller actually starts recording.
  AudioRecorder? _recorderInstance;
  AudioRecorder get _recorder => _recorderInstance ??= AudioRecorder();
  MicrophoneOwner? _owner;
  DateTime? _acquiredAt;
  Completer<void>? _releaseSignal;

  MicrophoneOwner? get currentOwner => _owner;
  String get currentOwnerLabel => _owner?.name ?? 'none';
  DateTime? get acquiredAt => _acquiredAt;

  Future<bool> acquire(
    MicrophoneOwner owner, {
    Duration timeout = const Duration(seconds: 2),
  }) async {
    if (_owner == null || _owner == owner) {
      _owner = owner;
      _acquiredAt = DateTime.now().toUtc();
      return true;
    }

    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      final remaining = deadline.difference(DateTime.now());
      final signal = _releaseSignal ??= Completer<void>();
      try {
        await signal.future.timeout(remaining);
      } catch (_) {
        return false;
      }
      if (_owner == null || _owner == owner) {
        _owner = owner;
        _acquiredAt = DateTime.now().toUtc();
        return true;
      }
    }
    return false;
  }

  void release(MicrophoneOwner owner) {
    if (_owner != owner) return;
    _owner = null;
    _acquiredAt = null;
    if (_releaseSignal != null && !_releaseSignal!.isCompleted) {
      _releaseSignal!.complete();
    }
    _releaseSignal = null;
  }

  void _requireOwner(MicrophoneOwner owner) {
    if (_owner != owner) {
      throw StateError(
        'MicrophoneManager: $owner is not the current microphone owner '
        '(owned by $currentOwnerLabel)',
      );
    }
  }

  /// Starts a raw PCM stream (used by the wake-word engine). Caller must
  /// already hold ownership via [acquire].
  Future<Stream<Uint8List>> startStream(
    MicrophoneOwner owner,
    RecordConfig config,
  ) async {
    _requireOwner(owner);
    return _recorder.startStream(config);
  }

  /// Starts file-based recording (used by the live voice loop / calibration).
  /// Caller must already hold ownership via [acquire].
  Future<void> start(
    MicrophoneOwner owner,
    RecordConfig config, {
    required String path,
  }) async {
    _requireOwner(owner);
    await _recorder.start(config, path: path);
  }

  Future<bool> isRecording() => _recorder.isRecording();

  Future<Amplitude> getAmplitude() => _recorder.getAmplitude();

  /// Stops recording if the given [owner] currently holds the microphone.
  /// Returns the recorded file path/blob URL (if any), matching
  /// `AudioRecorder.stop()`'s return value.
  Future<String?> stopRecording(MicrophoneOwner owner) async {
    if (_owner != owner) return null;
    if (await _recorder.isRecording()) {
      return _recorder.stop();
    }
    return null;
  }
}
