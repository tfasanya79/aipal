import 'dart:async';

import 'package:package_info_plus/package_info_plus.dart';

import 'api_client.dart';
import 'session_prefs.dart';

class SessionLogger {
  SessionLogger(this._apiFactory);

  final ApiClient? Function() _apiFactory;
  final List<Map<String, dynamic>> _pending = [];
  String? _buildLabel;
  Timer? _flushTimer;

  Future<String> _buildInfo() async {
    if (_buildLabel != null) return _buildLabel!;
    try {
      final info = await PackageInfo.fromPlatform();
      _buildLabel = '${info.version}+${info.buildNumber}';
    } catch (_) {
      _buildLabel = 'unknown';
    }
    return _buildLabel!;
  }

  Future<void> log(
    String sessionId,
    String eventType, {
    Map<String, dynamic>? payload,
  }) async {
    if (!await SessionPrefs.isRecordingEnabled()) return;
    if (sessionId.isEmpty) return;
    final build = await _buildInfo();
    final phaseTag = await SessionPrefs.phaseTag();
    _pending.add({
      'event_type': eventType,
      'payload': {...?payload, 'build': build},
      if (phaseTag != null) 'phase_tag': phaseTag,
    });
    _scheduleFlush(sessionId, phaseTag);
  }

  void _scheduleFlush(String sessionId, String? phaseTag) {
    _flushTimer?.cancel();
    _flushTimer = Timer(const Duration(milliseconds: 400), () {
      unawaited(_flush(sessionId, phaseTag));
    });
  }

  Future<void> _flush(String sessionId, String? phaseTag) async {
    if (_pending.isEmpty) return;
    final api = _apiFactory();
    if (api == null) return;
    final batch = List<Map<String, dynamic>>.from(_pending);
    _pending.clear();
    try {
      await api.postSessionEvents(
        sessionId: sessionId,
        phaseTag: phaseTag,
        events: batch,
      );
    } catch (_) {
      _pending.insertAll(0, batch);
    }
  }

  Future<void> flushNow(String sessionId) async {
    final phaseTag = await SessionPrefs.phaseTag();
    await _flush(sessionId, phaseTag);
  }
}
