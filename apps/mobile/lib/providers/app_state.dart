import 'dart:async';
import 'dart:convert';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../services/device_timezone.dart';
import '../services/calendar_service.dart';
import '../services/api_client.dart';
import '../services/live_session.dart';
import '../services/live_voice_loop.dart';
import '../services/notification_service.dart';
import '../services/session_logger.dart';
import '../services/session_prefs.dart';
import '../services/wake_background_service.dart';
import '../services/wake_word_prefs.dart';
import '../services/wake_word_service.dart';

class AppState extends ChangeNotifier {
  AppState() {
    if (_isAndroid) {
      FlutterForegroundTask.addTaskDataCallback(_onBackgroundWakeData);
    }
  }

  final _storage = const FlutterSecureStorage();
  bool authReady = false;
  String? token;
  Map<String, dynamic>? profile;
  List<Map<String, dynamic>> tasks = [];
  Map<String, dynamic>? todayView;
  Map<String, dynamic>? eveningPayload;
  Map<String, dynamic>? pendingPlanDraft;
  int selectedTab = 0;
  Map<String, dynamic>? focusTask;
  int focusSeconds = 25 * 60;
  final liveSession = LiveSession();
  LiveVoiceLoop? _voiceLoop;
  final _player = AudioPlayer();
  String? lastReply;
  String? lastTranscript;
  String? checkinBanner;
  String? suggestDayNotice;
  bool loading = false;
  bool _speaking = false;
  bool _processingTurn = false;
  int _turnGeneration = 0;
  WakeWordService? _wakeWord;
  bool wakeWordEnabled = false;
  bool wakeWordListening = false;
  bool wakeWordAvailable = !kIsWeb;
  final List<Timer> _nudgeTimers = [];
  late final SessionLogger _sessionLogger = SessionLogger(() => token != null ? api : null);
  String? _lastExportSessionId;

  ApiClient get api => ApiClient(token);

  String? get lastExportSessionId => _lastExportSessionId;

  bool get _isAndroid =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  String get _wakeName =>
      profile?['wake_name'] as String? ?? profile?['display_name'] as String? ?? 'friend';

  Map<String, dynamic>? get nextOpenTask {
    final up = todayView?['up_next'] as Map<String, dynamic>?;
    if (up != null) return up;
    final sections = todayView?['sections'] as Map<String, dynamic>?;
    final upcoming = (sections?['upcoming'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    return upcoming.isNotEmpty ? upcoming.first : null;
  }

  List<Map<String, dynamic>> get openTasksForReview {
    final sections = todayView?['sections'] as Map<String, dynamic>?;
    final now = (sections?['now'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final upcoming = (sections?['upcoming'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    return [...now, ...upcoming];
  }

  void goToTab(int index) {
    selectedTab = index;
    unawaited(syncWakeListener());
    notifyListeners();
  }

  /// Fast path for app launch: read stored token only; never blocks on network or wake.
  Future<void> loadStoredAuth() async {
    try {
      try {
        token = await _storage
            .read(key: 'token')
            .timeout(const Duration(seconds: 2));
      } on TimeoutException {
        token = null;
      } catch (_) {
        token = null;
      }
    } finally {
      authReady = true;
      notifyListeners();
    }
  }

  /// Post-frame bootstrap: profile validation, today view, wake listener.
  Future<void> finishBootstrap() async {
    try {
      if (token != null) {
        try {
          profile = await api.getProfile();
          await _syncDeviceTimezone();
          await _loadCheckinBanner();
          await refreshTodayView();
        } catch (_) {
          token = null;
          profile = null;
        }
      }
      await _loadWakePrefs();
      try {
        await syncWakeListener();
      } catch (_) {}
    } finally {
      notifyListeners();
    }
  }

  Future<void> _loadWakePrefs() async {
    wakeWordEnabled = await WakeWordPrefs.isEnabled();
  }

  Future<void> _syncDeviceTimezone() async {
    try {
      final deviceTz = await deviceIanaTimezone();
      final profileTz = profile?['timezone'] as String?;
      if (deviceTz != profileTz) {
        profile = await api.updateProfile({'timezone': deviceTz});
      }
    } catch (_) {}
  }

  Future<void> setWakeWordEnabled(bool enabled) async {
    wakeWordEnabled = enabled;
    await WakeWordPrefs.setEnabled(enabled);
    await syncWakeListener();
    notifyListeners();
  }

  Future<void> syncWakeListener() async {
    if (!wakeWordAvailable || token == null) {
      await _stopAllWakeListening();
      notifyListeners();
      return;
    }

    if (_isAndroid) {
      await _syncAndroidBackgroundWake();
      return;
    }

    final shouldListen = wakeWordEnabled &&
        selectedTab == 0 &&
        liveSession.state == LiveState.resting &&
        !_shouldSuppressWake();
    if (!shouldListen) {
      await _stopWakeListener();
      wakeWordListening = false;
      notifyListeners();
      return;
    }
    _wakeWord ??= WakeWordService(
      onWake: () => unawaited(_onWakeWordDetected()),
      shouldSuppress: _shouldSuppressWake,
    );
    if (!await _wakeWord!.init()) {
      wakeWordListening = false;
      notifyListeners();
      return;
    }
    await _wakeWord!.start();
    wakeWordListening = _wakeWord!.isListening;
    notifyListeners();
  }

  Future<void> _syncAndroidBackgroundWake() async {
    await _stopWakeListener();
    if (!wakeWordEnabled) {
      await WakeBackgroundService.stop();
      wakeWordListening = false;
      notifyListeners();
      return;
    }

    final suppressed =
        liveSession.state != LiveState.resting || _shouldSuppressWake();
    final running = await WakeBackgroundService.ensureRunning();
    if (running) {
      WakeBackgroundService.setSuppressed(suppressed);
      wakeWordListening = !suppressed;
    } else {
      wakeWordListening = false;
    }
    notifyListeners();
  }

  Future<void> _stopWakeListener() async {
    final svc = _wakeWord;
    if (svc != null) {
      await svc.stop();
    }
  }

  Future<void> _stopAllWakeListening() async {
    await _stopWakeListener();
    if (_isAndroid) {
      await WakeBackgroundService.stop();
    }
    wakeWordListening = false;
  }

  void _onBackgroundWakeData(Object data) {
    if (data is Map && data['event'] == 'wake') {
      unawaited(handleBackgroundWake());
    }
  }

  Future<void> handleBackgroundWake() async {
    if (liveSession.state != LiveState.resting) return;
    selectedTab = 0;
    WakeBackgroundService.setSuppressed(true);
    notifyListeners();
    await toggleLive();
  }

  Future<void> _onWakeWordDetected() async {
    if (liveSession.state != LiveState.resting) return;
    await _stopWakeListener();
    await toggleLive();
  }

  Future<void> _loadCheckinBanner() async {
    try {
      final payload = await api.checkinPayload();
      checkinBanner = payload['prompt'] as String?;
    } catch (_) {
      checkinBanner = null;
    }
  }

  Future<void> login(String email) async {
    final reg = await api.register(email);
    final devToken = reg['dev_token'] as String?;
    if (devToken == null) throw Exception('No dev token — configure SMTP for production');
    final auth = await ApiClient(null).verify(devToken);
    token = auth['access_token'] as String;
    await _storage.write(key: 'token', value: token);
    profile = await api.getProfile();
    await _loadCheckinBanner();
    await refreshTodayView();
    notifyListeners();
  }

  Future<void> updateProfile(Map<String, dynamic> data) async {
    profile = await api.updateProfile(data);
    notifyListeners();
  }

  Future<void> refreshTasks() async {
    final list = await api.listTasks();
    tasks = list.cast<Map<String, dynamic>>();
    notifyListeners();
  }

  Future<void> syncDeviceCalendar() async {
    if (token == null || kIsWeb) return;
    try {
      final events = await CalendarService().fetchTodayEvents();
      if (events.isNotEmpty) {
        await api.importCalendar(events);
      }
    } catch (_) {}
  }

  Future<void> refreshTodayView() async {
    if (token == null) return;
    try {
      unawaited(syncDeviceCalendar());
      todayView = await api.fetchTodayView();
      tasks = [
        ...?((todayView?['sections'] as Map?)?['now'] as List?),
        ...?((todayView?['sections'] as Map?)?['upcoming'] as List?),
        ...?((todayView?['sections'] as Map?)?['completed'] as List?),
      ].cast<Map<String, dynamic>>();
      await _rescheduleTaskNudges();
    } catch (_) {}
    notifyListeners();
  }

  void _cancelNudgeTimers() {
    for (final t in _nudgeTimers) {
      t.cancel();
    }
    _nudgeTimers.clear();
  }

  Future<void> _rescheduleTaskNudges() async {
    if (kIsWeb || token == null) return;
    _cancelNudgeTimers();
    final open = openTasksForReview;
    try {
      await NotificationService.instance.rescheduleTaskNudges(
        tasks: open,
        wakeName: _wakeName,
      );
    } catch (_) {}
    final now = DateTime.now();
    for (final task in open) {
      final dueRaw = task['due_at'] as String?;
      final id = task['id'] as int?;
      if (dueRaw == null || id == null) continue;
      DateTime dueLocal;
      try {
        dueLocal = DateTime.parse(dueRaw).toLocal();
      } catch (_) {
        continue;
      }
      final fireAt = dueLocal.subtract(
        const Duration(minutes: NotificationService.nudgeLeadMinutes),
      );
      final delay = fireAt.difference(now);
      if (delay.isNegative || delay.inDays > 0) continue;
      final hour = dueLocal.hour;
      if (hour >= 22 || hour < 7) continue;
      _nudgeTimers.add(
        Timer(delay, () => unawaited(handleForegroundNudge(id, NotificationService.nudgeLeadMinutes))),
      );
    }
  }

  Future<void> handleForegroundNudge(int taskId, int minutes) async {
    if (token == null) return;
    if (_speaking || _processingTurn) return;
    if (selectedTab != 0 && liveSession.state != LiveState.listening) return;
    try {
      final msg = await api.taskNudge(taskId: taskId, minutes: minutes);
      final text = msg['text'] as String?;
      if (text == null || text.isEmpty) return;
      lastReply = text;
      notifyListeners();
      final tts = await api.tts(text);
      await _playAudioResponse(tts);
    } catch (_) {}
  }

  Future<void> loadEveningPayload() async {
    eveningPayload = await api.eveningPayload();
    notifyListeners();
  }

  Future<void> createTask(String title) async {
    await api.createTask(title);
    await refreshTodayView();
  }

  Future<void> completeTask(int id) async {
    await api.patchTask(id, 'done');
    await refreshTodayView();
  }

  Future<void> updateTaskSchedule(int id, DateTime dueLocal, int minutes) async {
    await api.updateTask(id, {
      'due_at': dueLocal.toUtc().toIso8601String(),
      'estimated_minutes': minutes,
    });
    await refreshTodayView();
  }

  Future<void> breakdownTask(int id) async {
    loading = true;
    notifyListeners();
    try {
      await api.breakdownTask(id);
      await refreshTodayView();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> deferOpenTasks() async {
    await api.deferOpenTasks();
    await refreshTodayView();
  }

  Future<void> reorderUpcoming(List<Map<String, dynamic>> upcoming, int oldIndex, int newIndex) async {
    final items = List<Map<String, dynamic>>.from(upcoming);
    final moved = items.removeAt(oldIndex);
    items.insert(newIndex, moved);
    await api.reorderTasks(items.map((t) => t['id'] as int).toList());
    await refreshTodayView();
  }

  Future<void> reorderUpcomingLane(
    List<Map<String, dynamic>> upcoming,
    int priority,
    int oldIndex,
    int newIndex,
  ) async {
    final grouped = <int, List<Map<String, dynamic>>>{};
    for (final t in upcoming) {
      final p = (t['priority'] as int?) ?? 1;
      grouped.putIfAbsent(p, () => []).add(t);
    }
    final lane = List<Map<String, dynamic>>.from(grouped[priority] ?? []);
    final moved = lane.removeAt(oldIndex);
    lane.insert(newIndex, moved);
    grouped[priority] = lane;

    final ordered = <Map<String, dynamic>>[];
    for (final p in [2, 1, 0]) {
      ordered.addAll(grouped[p] ?? []);
    }
    await api.reorderTasks(ordered.map((t) => t['id'] as int).toList());
    await refreshTodayView();
  }

  Future<void> startFocus(Map<String, dynamic> task) async {
    final mins = task['estimated_minutes'] as int? ?? 25;
    focusSeconds = mins * 60;
    focusTask = task;
    await api.patchTask(task['id'] as int, 'in_progress');
    await refreshTodayView();
    notifyListeners();
  }

  Future<void> completeFocusTask() async {
    if (focusTask != null) {
      await completeTask(focusTask!['id'] as int);
    }
    cancelFocus();
  }

  void cancelFocus() {
    focusTask = null;
    notifyListeners();
  }

  bool _isSpeakingForVad() => _speaking;

  bool _shouldSuppressWake() =>
      _speaking || _processingTurn || liveSession.isActive;

  Future<void> toggleLive() async {
    if (token == null) return;
    if (liveSession.state == LiveState.resting) {
      final loop = LiveVoiceLoop(
        onSegment: _handleVoiceSegment,
        shouldSuppress: () => false,
        isSpeakingForVad: _isSpeakingForVad,
        thresholdDb: -45.0,
        thresholdDbSpeaking: -32.0,
        onSpeechStart: () {
          if (_speaking) {
            _turnGeneration++;
            _speaking = false;
            if (liveSession.isActive) {
              liveSession.state = LiveState.listening;
            }
            unawaited(_player.stop());
            notifyListeners();
          }
        },
      );
      try {
        if (!await loop.ensureMicPermission()) {
          lastReply = 'Microphone permission is required for Live voice mode.';
          notifyListeners();
          return;
        }
        await liveSession.start(token!, (msg) {
          if (msg['type'] == 'reply') {
            lastReply = msg['text'] as String?;
            notifyListeners();
          }
        });
        _voiceLoop = loop;
        await loop.start();
        unawaited(_playLiveGreeting());
      } catch (e) {
        lastReply = e.toString();
        await _stopVoiceLoop();
        await liveSession.stop();
      }
    } else {
      await _stopVoiceLoop();
      await liveSession.stop();
      _turnGeneration++;
    }
    await syncWakeListener();
    notifyListeners();
  }

  Future<void> _stopVoiceLoop() async {
    final loop = _voiceLoop;
    _voiceLoop = null;
    if (loop != null) {
      await loop.stop();
      await loop.dispose();
    }
  }

  Future<void> _playLiveGreeting() async {
    try {
      final showIntro = wakeWordEnabled && !await WakeWordPrefs.introShown();
      final greeting = await api.liveGreeting(
        inLive: true,
        wakeEnabled: wakeWordEnabled,
        showWakeIntro: showIntro,
      );
      if (showIntro) {
        await WakeWordPrefs.markIntroShown();
      }
      final text = greeting['text'] as String?;
      if (text == null || text.isEmpty) return;
      lastReply = text;
      notifyListeners();
      final tts = await api.tts(text);
      await _playAudioResponse(tts);
      await syncWakeListener();
    } catch (_) {}
  }

  Future<void> _handleVoiceSegment(List<int> bytes) async {
    if (token == null || _processingTurn) return;
    final turnGen = ++_turnGeneration;
    _processingTurn = true;
    liveSession.state = LiveState.thinking;
    notifyListeners();
    var shouldRefreshToday = false;
    try {
      const filename = 'turn.webm';
      final res = await api.audioTurn(
        bytes,
        filename: kIsWeb ? filename : 'turn.m4a',
        sessionId: liveSession.sessionId,
      );
      if (turnGen != _turnGeneration) return;
      final returnedSid = res['session_id'] as String?;
      if (returnedSid != null && (liveSession.sessionId == null || liveSession.sessionId!.isEmpty)) {
        liveSession.sessionId = returnedSid;
      }
      lastTranscript = res['transcript'] as String?;
      lastReply = res['reply'] as String?;
      if (res['draft_confirmed'] == true) {
        pendingPlanDraft = null;
        shouldRefreshToday = true;
      } else {
        pendingPlanDraft = res['plan_draft'] as Map<String, dynamic>?;
        if (pendingPlanDraft == null) {
          await loadPlanDraft();
        }
        if (pendingPlanDraft != null) {
          shouldRefreshToday = true;
        }
        if (res['tool_actions'] is List && (res['tool_actions'] as List).isNotEmpty) {
          shouldRefreshToday = true;
        }
      }
      if (turnGen != _turnGeneration) return;
      await _playAudioResponse(res, turnGen: turnGen);
    } catch (e) {
      if (turnGen == _turnGeneration) {
        lastReply = 'Voice turn failed: $e';
      }
    } finally {
      _processingTurn = false;
      if (liveSession.isActive) {
        liveSession.state = LiveState.listening;
      }
      await syncWakeListener();
      notifyListeners();
      if (shouldRefreshToday) {
        unawaited(refreshTodayView());
      }
    }
  }

  Future<void> _playAudioResponse(Map<String, dynamic> res, {int? turnGen}) async {
    final audioB64 = res['audio_base64'] as String?;
    final mime = res['audio_mime'] as String? ?? 'audio/mpeg';
    if (audioB64 == null || audioB64.isEmpty) return;
    if (turnGen != null && turnGen != _turnGeneration) return;
    _speaking = true;
    liveSession.state = LiveState.speaking;
    notifyListeners();
    final completer = Completer<void>();
    late StreamSubscription<void> sub;
    sub = _player.onPlayerComplete.listen((_) {
      sub.cancel();
      if (!completer.isCompleted) completer.complete();
    });
    await _player.play(BytesSource(base64Decode(audioB64), mimeType: mime));
    await completer.future.timeout(const Duration(minutes: 2), onTimeout: () {});
    if (turnGen != null && turnGen != _turnGeneration) return;
    _speaking = false;
    if (liveSession.isActive) {
      liveSession.state = LiveState.listening;
    }
    await syncWakeListener();
    notifyListeners();
  }

  @override
  void dispose() {
    _cancelNudgeTimers();
    if (_isAndroid) {
      FlutterForegroundTask.removeTaskDataCallback(_onBackgroundWakeData);
      unawaited(WakeBackgroundService.stop());
    }
    unawaited(_wakeWord?.dispose());
    super.dispose();
  }

  Future<Map<String, dynamic>> sendTextTurn(String text, {String? sessionId}) async {
    if (liveSession.isActive) {
      liveSession.sendText(text);
      return {'reply': text};
    }
    final sid = sessionId ?? liveSession.sessionId ?? 'text';
    final res = await api.textTurn(text, sessionId: sid);
    _lastExportSessionId = res['session_id'] as String? ?? sid;
    await _sessionLogger.log(
      _lastExportSessionId!,
      'text_turn',
      payload: {'text_len': text.length, 'reply_len': (res['reply'] as String? ?? '').length},
    );
    await _sessionLogger.flushNow(_lastExportSessionId!);
    lastReply = res['reply'] as String?;
    pendingPlanDraft = res['plan_draft'] as Map<String, dynamic>?;
    await refreshTodayView();
    notifyListeners();
    return res;
  }

  Future<Map<String, dynamic>?> exportLastSession() async {
    final sid = _lastExportSessionId ?? liveSession.sessionId;
    if (sid == null || sid.isEmpty) return null;
    await _sessionLogger.flushNow(sid);
    return api.exportSession(sid);
  }

  Future<bool> sessionRecordingEnabled() => SessionPrefs.isRecordingEnabled();

  Future<void> setSessionRecordingEnabled(bool value) => SessionPrefs.setRecordingEnabled(value);

  Future<String?> sessionPhaseTag() => SessionPrefs.phaseTag();

  Future<void> setSessionPhaseTag(String? value) => SessionPrefs.setPhaseTag(value);

  Future<void> confirmPlanDraft() async {
    await api.confirmPlanDraft();
    pendingPlanDraft = null;
    await refreshTodayView();
    notifyListeners();
  }

  Future<void> discardPlanDraft() async {
    await api.discardPlanDraft();
    pendingPlanDraft = null;
    notifyListeners();
  }

  Future<void> loadPlanDraft() async {
    pendingPlanDraft = await api.fetchPlanDraft();
    notifyListeners();
  }

  Future<void> suggestDayPlan({String? template}) async {
    loading = true;
    suggestDayNotice = null;
    notifyListeners();
    try {
      pendingPlanDraft = await api.suggestDay(template: template);
      if (pendingPlanDraft == null) {
        suggestDayNotice =
            'No plan suggestions right now. Try a routine chip above or add a task first.';
      }
    } catch (e) {
      suggestDayNotice = 'Could not suggest a plan. Check your connection and try again.';
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  void clearSuggestDayNotice() {
    suggestDayNotice = null;
    notifyListeners();
  }
}
