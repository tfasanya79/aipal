import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:uuid/uuid.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config.dart';
import 'audio_playback_queue.dart';
import 'pcm_stream_recorder.dart';

typedef LiveVoiceMessageHandler = void Function(Map<String, dynamic> msg);

/// Full-duplex Live Voice v2 session over WebSocket.
class LiveVoiceSession {
  LiveVoiceSession({
    required this.onMessage,
    this.onSpeechStart,
    this.isSpeakingForVad,
    this.silenceMs = 800,
    this.maxSegmentMs = 10000,
    this.thresholdDb = -35.0,
    this.thresholdDbSpeaking = -25.0,
  });

  final LiveVoiceMessageHandler onMessage;
  final void Function()? onSpeechStart;
  final bool Function()? isSpeakingForVad;
  final int silenceMs;
  final int maxSegmentMs;
  final double thresholdDb;
  final double thresholdDbSpeaking;

  static const _tickMs = 120;
  static const _uuid = Uuid();

  WebSocketChannel? _channel;
  final PcmStreamRecorder _recorder = PcmStreamRecorder();
  AudioPlaybackQueue? _playback;
  Timer? _vadTicker;
  String? sessionId;
  String? _currentTurnId;
  bool _active = false;
  bool _inSegment = false;
  int _silenceAccumMs = 0;
  int _segmentStartedAt = 0;
  int _dynamicSilenceMs = 800;
  bool _speaking = false;

  bool get isActive => _active;
  bool get isSpeaking => _speaking;

  Future<bool> ensureMicPermission() async {
    return _recorder.ensureMicPermission();
  }

  Future<void> start(String token) async {
    await stop();
    _playback = AudioPlaybackQueue();
    _channel = WebSocketChannel.connect(Uri.parse(AppConfig.wsUrl(token)));
    _active = true;
    _dynamicSilenceMs = silenceMs;

    _channel!.stream.listen(_onWsMessage, onDone: () {
      _active = false;
    });

    _recorder.onPcm = _onPcmFrame;
    await _recorder.start();

    _vadTicker = Timer.periodic(const Duration(milliseconds: _tickMs), (_) {
      unawaited(_vadTick());
    });
  }

  Future<void> stop() async {
    _active = false;
    _vadTicker?.cancel();
    _vadTicker = null;
    try {
      _channel?.sink.add(jsonEncode({'type': 'end'}));
    } catch (_) {}
    await _channel?.sink.close();
    _channel = null;
    await _recorder.stop();
    await _playback?.dispose();
    _playback = null;
    sessionId = null;
    _currentTurnId = null;
    _inSegment = false;
    _speaking = false;
  }

  Future<void> dispose() async {
    await stop();
    await _recorder.dispose();
    _recorder.onPcm = null;
  }

  void sendInterrupt() {
    final turnId = _currentTurnId;
    if (turnId == null) return;
    _channel?.sink.add(jsonEncode({'type': 'interrupt', 'turn_id': turnId}));
    unawaited(_playback?.flush());
    _speaking = false;
  }

  void sendTextTurn(String text) {
    final turnId = _uuid.v4();
    _currentTurnId = turnId;
    _channel?.sink.add(jsonEncode({'type': 'text_turn', 'text': text, 'turn_id': turnId}));
  }

  void _onPcmFrame(Uint8List bytes) {
    if (!_active || _channel == null) return;
    final turnId = _currentTurnId ??= _uuid.v4();
    _channel!.sink.add(jsonEncode({
      'type': 'audio_frame',
      'turn_id': turnId,
      'data': base64Encode(bytes),
    }));
  }

  void _onWsMessage(dynamic data) {
    final msg = jsonDecode(data as String) as Map<String, dynamic>;
    final type = msg['type'] as String?;
    if (type == 'session_started') {
      sessionId = msg['session_id'] as String?;
    }
    if (type == 'state') {
      final s = msg['state'] as String?;
      _speaking = s == 'speaking';
    }
    if (type == 'audio_chunk') {
      final b64 = msg['data'] as String?;
      final mime = msg['mime'] as String? ?? 'audio/mpeg';
      if (b64 != null && b64.isNotEmpty) {
        unawaited(_playback?.enqueue(bytes: base64Decode(b64), mime: mime));
        _speaking = true;
      }
    }
    if (type == 'turn_cancelled') {
      unawaited(_playback?.flush());
      _speaking = false;
      _currentTurnId = null;
    }
    if (type == 'turn_complete') {
      _speaking = false;
      _currentTurnId = null;
    }
    onMessage(msg);
  }

  Future<void> _vadTick() async {
    if (!_active) return;
    final amp = await _recorder.getAmplitude();
    final threshold = (_speaking || (isSpeakingForVad?.call() ?? false))
        ? thresholdDbSpeaking
        : thresholdDb;
    final speaking = amp.current > threshold;

    if (speaking) {
      _silenceAccumMs = 0;
      if (!_inSegment) {
        _inSegment = true;
        _segmentStartedAt = DateTime.now().millisecondsSinceEpoch;
        _currentTurnId ??= _uuid.v4();
        _channel?.sink.add(jsonEncode({'type': 'speech_start', 'turn_id': _currentTurnId}));
        if (_speaking) {
          sendInterrupt();
        }
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
    if (!_inSegment) return;
    _inSegment = false;
    _silenceAccumMs = 0;
    final turnId = _currentTurnId;
    if (turnId != null) {
      _channel?.sink.add(jsonEncode({'type': 'speech_end', 'turn_id': turnId}));
    }
    final elapsed = DateTime.now().millisecondsSinceEpoch - _segmentStartedAt;
    _dynamicSilenceMs = max(700, min(1700, (elapsed * 0.25).round()));
  }
}
