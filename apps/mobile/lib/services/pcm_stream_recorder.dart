import 'dart:async';
import 'dart:typed_data';

import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

/// Continuous 16 kHz mono PCM stream for Live Voice v2.
class PcmStreamRecorder {
  PcmStreamRecorder({this.onPcm});

  void Function(Uint8List bytes)? onPcm;

  final AudioRecorder _recorder = AudioRecorder();
  StreamSubscription<Uint8List>? _sub;
  bool _active = false;

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
    final stream = await _recorder.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
    ));
    _sub = stream.listen(onPcm);
    _active = true;
  }

  Future<void> stop() async {
    _active = false;
    await _sub?.cancel();
    _sub = null;
    if (await _recorder.isRecording()) {
      await _recorder.stop();
    }
  }

  Future<void> dispose() async {
    await stop();
    await _recorder.dispose();
  }

  Future<Amplitude> getAmplitude() => _recorder.getAmplitude();
}
