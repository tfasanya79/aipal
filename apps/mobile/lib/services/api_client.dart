import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';

class ApiClient {
  ApiClient(this.token);

  final String? token;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  Future<Map<String, dynamic>> register(String email) async {
    final r = await http.post(
      Uri.parse('${AppConfig.apiBase}/auth/register'),
      headers: _headers,
      body: jsonEncode({'email': email}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> verify(String magicToken) async {
    final r = await http.post(
      Uri.parse('${AppConfig.apiBase}/auth/verify'),
      headers: _headers,
      body: jsonEncode({'token': magicToken}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getProfile() async {
    final r = await http.get(Uri.parse('${AppConfig.apiBase}/profile'), headers: _headers);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateProfile(Map<String, dynamic> body) async {
    final r = await http.put(
      Uri.parse('${AppConfig.apiBase}/profile'),
      headers: _headers,
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listTasks() async {
    final r = await http.get(Uri.parse('${AppConfig.apiBase}/tasks'), headers: _headers);
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> createTask(String title) async {
    final r = await http.post(
      Uri.parse('${AppConfig.apiBase}/tasks'),
      headers: _headers,
      body: jsonEncode({'title': title, 'source': 'text'}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> patchTask(int id, String status, {Map<String, dynamic>? extra}) async {
    final body = <String, dynamic>{'status': status, ...?extra};
    final r = await http.patch(
      Uri.parse('${AppConfig.apiBase}/tasks/$id'),
      headers: _headers,
      body: jsonEncode(body),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> fetchTodayView() async {
    final r = await http.get(Uri.parse('${AppConfig.apiBase}/tasks/today-view'), headers: _headers);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<void> reorderTasks(List<int> orderedIds) async {
    await http.post(
      Uri.parse('${AppConfig.apiBase}/tasks/reorder'),
      headers: _headers,
      body: jsonEncode({'ordered_ids': orderedIds}),
    );
  }

  Future<List<dynamic>> breakdownTask(int id) async {
    final r = await http.post(
      Uri.parse('${AppConfig.apiBase}/tasks/$id/breakdown'),
      headers: _headers,
    );
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<int> deferOpenTasks() async {
    final r = await http.post(
      Uri.parse('${AppConfig.apiBase}/tasks/defer-open'),
      headers: _headers,
    );
    return (jsonDecode(r.body) as Map<String, dynamic>)['deferred'] as int? ?? 0;
  }

  Future<Map<String, dynamic>> taskSummary() async {
    final r = await http.get(Uri.parse('${AppConfig.apiBase}/tasks/summary'), headers: _headers);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> morningPayload() async {
    final r = await http.get(Uri.parse('${AppConfig.apiBase}/daily/morning-payload'), headers: _headers);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> eveningPayload() async {
    final r = await http.get(Uri.parse('${AppConfig.apiBase}/daily/evening-payload'), headers: _headers);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> textTurn(String text, {String? sessionId}) async {
    final r = await http.post(
      Uri.parse('${AppConfig.apiBase}/turn/text'),
      headers: _headers,
      body: jsonEncode({'text': text, if (sessionId != null) 'session_id': sessionId}),
    );
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>?> suggestDay({String? template}) async {
    final r = await http.post(
      Uri.parse('${AppConfig.apiBase}/tasks/suggest-day'),
      headers: _headers,
      body: jsonEncode({if (template != null) 'template': template}),
    );
    if (r.statusCode >= 400) {
      throw Exception('Suggest day failed (${r.statusCode}): ${r.body}');
    }
    final body = jsonDecode(r.body) as Map<String, dynamic>;
    return body['plan_draft'] as Map<String, dynamic>?;
  }

  Future<Map<String, dynamic>?> fetchPlanDraft() async {
    final r = await http.get(Uri.parse('${AppConfig.apiBase}/tasks/plan-draft'), headers: _headers);
    if (r.statusCode == 200 && r.body.trim().isNotEmpty && r.body.trim() != 'null') {
      return jsonDecode(r.body) as Map<String, dynamic>;
    }
    return null;
  }

  Future<List<dynamic>> confirmPlanDraft() async {
    final r = await http.post(
      Uri.parse('${AppConfig.apiBase}/tasks/plan-draft/confirm'),
      headers: _headers,
    );
    final body = jsonDecode(r.body) as Map<String, dynamic>;
    return (body['created'] as List?) ?? [];
  }

  Future<void> discardPlanDraft() async {
    await http.post(
      Uri.parse('${AppConfig.apiBase}/tasks/plan-draft/discard'),
      headers: _headers,
    );
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
    final r = await http.get(uri, headers: _headers);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> checkinPayload() async {
    final r = await http.get(Uri.parse('${AppConfig.apiBase}/daily/checkin-payload'), headers: _headers);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> taskNudge({required int taskId, int minutes = 12}) async {
    final uri = Uri.parse('${AppConfig.apiBase}/daily/task-nudge').replace(
      queryParameters: {'task_id': '$taskId', 'minutes': '$minutes'},
    );
    final r = await http.get(uri, headers: _headers);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> tts(String text) async {
    final r = await http.post(
      Uri.parse('${AppConfig.apiBase}/turn/tts'),
      headers: _headers,
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
    final streamed = await req.send();
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode >= 400) {
      throw Exception('Audio turn failed (${streamed.statusCode}): $body');
    }
    return jsonDecode(body) as Map<String, dynamic>;
  }

  Future<int> importCalendar(List<Map<String, dynamic>> events) async {
    final r = await http.post(
      Uri.parse('${AppConfig.apiBase}/calendar/import'),
      headers: _headers,
      body: jsonEncode({'events': events}),
    );
    return (jsonDecode(r.body) as Map<String, dynamic>)['imported'] as int;
  }
}
