import 'dart:async';
import 'dart:convert';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../config.dart';
import '../services/api_client.dart';
import '../services/live_session.dart';
import '../services/live_voice_loop.dart';
import '../services/live_voice_session.dart';
import '../services/notification_service.dart';
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
  LiveVoiceSession? _liveVoiceV2;
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

  ApiClient get api => ApiClient(token);

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

  Future<void> loadStoredAuth() async {
    try {
      token = await _storage.read(key: 'token');
      if (token != null) {
        try {
          profile = await api.getProfile();
          await _loadCheckinBanner();
          await refreshTodayView();
        } catch (_) {
          token = null;
        }
      }
      await _loadWakePrefs();
      await syncWakeListener();
    } finally {
      authReady = true;
      notifyListeners();
    }
  }

  Future<void> _loadWakePrefs() async {
    wakeWordEnabled = await WakeWordPrefs.isEnabled();
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

  Future<void> refreshTodayView() async {
    if (token == null) return;
    try {
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

  bool get _liveActive => _liveVoiceV2?.isActive ?? liveSession.isActive;

  bool _shouldSuppressLiveVad() => _processingTurn && _liveVoiceV2 == null;

  bool _isSpeakingForVad() => _speaking;

  bool _shouldSuppressWake() =>
      _speaking || _processingTurn || _liveActive;

  Future<void> toggleLive() async {
    if (token == null) return;
    if (liveSession.state == LiveState.resting) {
      final useV2 = AppConfig.liveVoiceV2 && !kIsWeb;
      if (useV2) {
        final session = LiveVoiceSession(
          onMessage: _handleLiveV2Message,
          isSpeakingForVad: _isSpeakingForVad,
          onSpeechStart: () {
            lastReply = null;
            lastTranscript = null;
            if (_speaking || (_liveVoiceV2?.isSpeaking ?? false)) {
              _turnGeneration++;
              _speaking = false;
              liveSession.state = LiveState.listening;
              notifyListeners();
            }
          },
        );
        try {
          if (!await session.ensureMicPermission()) {
            lastReply = 'Microphone permission is required for Live voice mode.';
            notifyListeners();
            return;
          }
          await session.start(token!);
          _liveVoiceV2 = session;
          liveSession.state = LiveState.listening;
          liveSession.sessionId = session.sessionId;
          unawaited(_playLiveGreeting(useWsPath: true));
        } catch (e) {
          lastReply = e.toString();
          await _stopLiveV2();
        }
      } else {
        final loop = LiveVoiceLoop(
          onSegment: _handleVoiceSegment,
          shouldSuppress: _shouldSuppressLiveVad,
          isSpeakingForVad: _isSpeakingForVad,
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
      }
    } else {
      await _stopVoiceLoop();
      await _stopLiveV2();
      await liveSession.stop();
      _turnGeneration++;
    }
    await syncWakeListener();
    notifyListeners();
  }

  Future<void> _stopLiveV2() async {
    final session = _liveVoiceV2;
    _liveVoiceV2 = null;
    if (session != null) {
      await session.dispose();
    }
    liveSession.state = LiveState.resting;
    liveSession.sessionId = null;
  }

  @visibleForTesting
  void handleLiveV2MessageForTest(Map<String, dynamic> msg) => _handleLiveV2Message(msg);

  void _handleLiveV2Message(Map<String, dynamic> msg) {
    final type = msg['type'] as String?;
    if (type == 'session_started') {
      liveSession.sessionId = msg['session_id'] as String?;
    }
    if (type == 'state') {
      final s = msg['state'] as String?;
      if (s == 'thinking') {
        liveSession.state = LiveState.thinking;
        lastReply = null;
      }
      if (s == 'listening') liveSession.state = LiveState.listening;
      if (s == 'speaking') {
        liveSession.state = LiveState.speaking;
        _speaking = true;
      }
    }
    if (type == 'transcript_partial') {
      lastTranscript = msg['text'] as String?;
    }
    if (type == 'transcript_final') {
      lastTranscript = msg['text'] as String?;
      lastReply = null;
    }
    if (type == 'reply_delta') {
      final delta = msg['text'] as String? ?? '';
      lastReply = '${lastReply ?? ''}$delta';
    }
    if (type == 'turn_complete') {
      _processingTurn = false;
      _speaking = false;
      lastReply = msg['reply'] as String? ?? lastReply;
      if (msg['draft_confirmed'] == true) {
        pendingPlanDraft = null;
        unawaited(refreshTodayView());
      } else {
        pendingPlanDraft = msg['plan_draft'] as Map<String, dynamic>?;
        if (pendingPlanDraft == null) {
          unawaited(loadPlanDraft());
        }
        if (msg['tool_actions'] is List && (msg['tool_actions'] as List).isNotEmpty) {
          unawaited(refreshTodayView());
        }
      }
      liveSession.state = LiveState.listening;
    }
    if (type == 'turn_cancelled') {
      _speaking = false;
      liveSession.state = LiveState.listening;
    }
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

  Future<void> _playLiveGreeting({bool useWsPath = false}) async {
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
      if (useWsPath && (_liveVoiceV2?.isActive ?? false)) {
        _liveVoiceV2!.sendTextTurn(text);
        await syncWakeListener();
        return;
      }
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
    if (_liveVoiceV2?.isActive ?? false) {
      _liveVoiceV2!.sendTextTurn(text);
      liveSession.state = LiveState.thinking;
      notifyListeners();
      return {'reply': text};
    }
    if (liveSession.isActive) {
      liveSession.sendText(text);
      return {'reply': text};
    }
    final res = await api.textTurn(text, sessionId: sessionId);
    lastReply = res['reply'] as String?;
    pendingPlanDraft = res['plan_draft'] as Map<String, dynamic>?;
    await refreshTodayView();
    notifyListeners();
    return res;
  }

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
