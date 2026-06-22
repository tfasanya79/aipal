import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';

class ApiClient {
  ApiClient(this.token);

  static const _timeout = Duration(seconds: 12);

  final String? token;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  Future<http.Response> _get(Uri uri) =>
      http.get(uri, headers: _headers).timeout(_timeout);

  Future<http.Response> _post(Uri uri, {Object? body}) =>
      http.post(uri, headers: _headers, body: body).timeout(_timeout);

  Future<http.Response> _put(Uri uri, {Object? body}) =>
      http.put(uri, headers: _headers, body: body).timeout(_timeout);

  Future<http.Response> _patch(Uri uri, {Object? body}) =>
      http.patch(uri, headers: _headers, body: body).timeout(_timeout);

  Future<Map<String, dynamic>> register(String email) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/auth/register'),
      body: jsonEncode({'email': email}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> verify(String magicToken) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/auth/verify'),
      body: jsonEncode({'token': magicToken}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getProfile() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/profile'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateProfile(Map<String, dynamic> body) async {
    final r = await _put(
      Uri.parse('${AppConfig.apiBase}/profile'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listTasks() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/tasks'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createTask(String title) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/tasks'),
      body: jsonEncode({'title': title, 'source': 'text'}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> patchTask(int id, String status, {Map<String, dynamic>? extra}) async {
    final body = <String, dynamic>{'status': status, ...?extra};
    final r = await _patch(
      Uri.parse('${AppConfig.apiBase}/tasks/$id'),
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateTask(int id, Map<String, dynamic> fields) async {
    final r = await _patch(
      Uri.parse('${AppConfig.apiBase}/tasks/$id'),
      body: jsonEncode(fields),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> fetchTodayView() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/tasks/today-view'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<void> reorderTasks(List<int> orderedIds) async {
    await _post(
      Uri.parse('${AppConfig.apiBase}/tasks/reorder'),
      body: jsonEncode({'ordered_ids': orderedIds}),
    );
  }

  Future<List<dynamic>> breakdownTask(int id) async {
    final r = await _post(Uri.parse('${AppConfig.apiBase}/tasks/$id/breakdown'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<int> deferOpenTasks() async {
    final r = await _post(Uri.parse('${AppConfig.apiBase}/tasks/defer-open'));
    return (jsonDecode(r.body) as Map<String, dynamic>)['deferred'] as int? ?? 0;
  }

  Future<Map<String, dynamic>> taskSummary() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/tasks/summary'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> morningPayload() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/daily/morning-payload'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> eveningPayload() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/daily/evening-payload'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> textTurn(String text, {String? sessionId}) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/turn/text'),
      body: jsonEncode({'text': text, if (sessionId != null) 'session_id': sessionId}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>?> suggestDay({String? template}) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/tasks/suggest-day'),
      body: jsonEncode({if (template != null) 'template': template}),
    );
    if (r.statusCode >= 400) {
      throw Exception('Suggest day failed (${r.statusCode}): ${r.body}');
    }
    final body = jsonDecode(r.body) as Map<String, dynamic>;
    return body['plan_draft'] as Map<String, dynamic>?;
  }

  Future<Map<String, dynamic>?> fetchPlanDraft() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/tasks/plan-draft'));
    if (r.statusCode == 200 && r.body.trim().isNotEmpty && r.body.trim() != 'null') {
      return jsonDecode(r.body) as Map<String, dynamic>;
    }
    return null;
  }

  Future<List<dynamic>> confirmPlanDraft() async {
    final r = await _post(Uri.parse('${AppConfig.apiBase}/tasks/plan-draft/confirm'));
    final body = jsonDecode(r.body) as Map<String, dynamic>;
    return (body['created'] as List?) ?? [];
  }

  Future<void> discardPlanDraft() async {
    await _post(Uri.parse('${AppConfig.apiBase}/tasks/plan-draft/discard'));
  }

  Future<Map<String, dynamic>> liveGreeting({
    bool inLive = false,
    bool wakeEnabled = false,
    bool showWakeIntro = false,
  }) async {
    final params = <String, String>{};
    if (inLive) params['in_live'] = 'true';
    if (wakeEnabled) params['wake_enabled'] = 'true';
    if (showWakeIntro) params['show_wake_intro'] = 'true';
    final uri = Uri.parse('${AppConfig.apiBase}/daily/live-greeting').replace(
      queryParameters: params.isEmpty ? null : params,
    );
    final r = await _get(uri);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> checkinPayload() async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/daily/checkin-payload'));
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> taskNudge({required int taskId, int minutes = 12}) async {
    final uri = Uri.parse('${AppConfig.apiBase}/daily/task-nudge').replace(
      queryParameters: {'task_id': '$taskId', 'minutes': '$minutes'},
    );
    final r = await _get(uri);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> tts(String text) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/turn/tts'),
      body: jsonEncode({'text': text}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> audioTurn(
    List<int> bytes, {
    String filename = 'turn.m4a',
    String? sessionId,
  }) async {
    final req = http.MultipartRequest('POST', Uri.parse('${AppConfig.apiBase}/turn/audio'));
    if (token != null) req.headers['Authorization'] = 'Bearer $token';
    if (sessionId != null && sessionId.isNotEmpty) {
      req.fields['session_id'] = sessionId;
    }
    req.files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));
    final streamed = await req.send().timeout(_timeout);
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode >= 400) {
      throw Exception('Audio turn failed (${streamed.statusCode}): $body');
    }
    return jsonDecode(body) as Map<String, dynamic>;
  }

  Future<int> importCalendar(List<Map<String, dynamic>> events) async {
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/calendar/import'),
      body: jsonEncode({'events': events}),
    );
    return (jsonDecode(r.body) as Map<String, dynamic>)['imported'] as int;
  }

  Future<Map<String, dynamic>> postSessionEvents({
    required String sessionId,
    String? phaseTag,
    required List<Map<String, dynamic>> events,
  }) async {
    final body = <String, dynamic>{
      'session_id': sessionId,
      if (phaseTag != null) 'phase_tag': phaseTag,
      'events': events
          .map(
            (e) => {
              'event_type': e['event_type'],
              'payload': e['payload'] ?? {},
              if (e['phase_tag'] != null) 'phase_tag': e['phase_tag'],
            },
          )
          .toList(),
    };
    final r = await _post(
      Uri.parse('${AppConfig.apiBase}/sessions/events'),
      body: jsonEncode(body),
    );
    if (r.statusCode >= 400) {
      throw Exception('Session events failed (${r.statusCode}): ${r.body}');
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> recentSessions({int limit = 5}) async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/sessions/recent?limit=$limit'));
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> exportSession(String sessionId) async {
    final r = await _get(Uri.parse('${AppConfig.apiBase}/sessions/$sessionId/export'));
    if (r.statusCode >= 400) {
      throw Exception('Export failed (${r.statusCode}): ${r.body}');
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }
}
