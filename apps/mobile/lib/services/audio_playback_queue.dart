import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';

/// Plays TTS audio chunks sequentially; supports flush on interrupt.
class AudioPlaybackQueue {
  AudioPlaybackQueue({AudioPlayer? player, this.onIdle}) : _player = player ?? AudioPlayer();

  final AudioPlayer _player;
  final List<_QueuedChunk> _queue = [];
  bool _playing = false;
  bool _disposed = false;
  StreamSubscription<void>? _completeSub;
  void Function()? onIdle;

  bool get isPlaying => _playing;

  Future<void> enqueue({required Uint8List bytes, required String mime}) async {
    if (_disposed) return;
    _queue.add(_QueuedChunk(bytes: bytes, mime: mime));
    if (!_playing) {
      await _playNext();
    }
  }

  Future<void> flush() async {
    _queue.clear();
    _playing = false;
    await _completeSub?.cancel();
    _completeSub = null;
    await _player.stop();
  }

  Future<void> dispose() async {
    _disposed = true;
    await flush();
    await _player.dispose();
  }

  Future<void> _playNext() async {
    if (_disposed || _queue.isEmpty) {
      final wasPlaying = _playing;
      _playing = false;
      if (wasPlaying) {
        onIdle?.call();
      }
      return;
    }
    _playing = true;
    final chunk = _queue.removeAt(0);
    final completer = Completer<void>();
    await _completeSub?.cancel();
    _completeSub = _player.onPlayerComplete.listen((_) {
      if (!completer.isCompleted) completer.complete();
    });
    await _player.play(BytesSource(chunk.bytes, mimeType: chunk.mime));
    await completer.future.timeout(const Duration(minutes: 2), onTimeout: () {});
    await _playNext();
  }
}

class _QueuedChunk {
  _QueuedChunk({required this.bytes, required this.mime});
  final Uint8List bytes;
  final String mime;
}
