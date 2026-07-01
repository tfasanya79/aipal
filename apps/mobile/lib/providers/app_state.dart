import 'dart:async';
import 'dart:convert';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../services/device_timezone.dart';
import '../services/device_location.dart';
import '../services/calendar_service.dart';
import '../services/api_client.dart';
import '../services/live_session.dart';
import '../services/live_voice_loop.dart';
import '../services/music_command_service.dart';
import '../services/notification_service.dart';
import '../services/session_logger.dart';
import '../services/session_prefs.dart';
import '../services/wake_background_service.dart';
import '../services/wake_word_engine.dart';
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
  bool _inConversation = false;
  bool _awaitingGreeting = false;
  int _turnGeneration = 0;
  static const _conversationIdleSeconds = 18;
  Timer? _conversationIdleTimer;
  int _consecutiveDiscards = 0;
  int _consecutiveTurnTimeouts = 0;
  bool _softPromptShown = false;
  DateTime? _lastDiscardAt;
  Completer<void>? _wakeEngineReadyCompleter;
  WakeWordService? _wakeWord;
  bool wakeWordEnabled = false;
  bool wakeWordListening = false;
  String? wakeWordError;
  bool wakeWordAvailable = !kIsWeb;
  final List<Timer> _nudgeTimers = [];
  bool _appInForeground = true;
  AppLifecycleState _lifecycle = AppLifecycleState.resumed;
  String? _activeWakeRoute;
  bool _wakePausedForCalibration = false;
  Timer? _wakeRetryTimer;
  int _wakeRetryAttempts = 0;
  Timer? _syncWakeDebounce;
  Timer? _foregroundDebounce;
  Timer? _wakeSuppressResyncTimer;
  Future<void> _syncWakeChain = Future.value();
  bool _toggleLiveInProgress = false;
  DateTime? _wakeSuppressUntil;
  static const _wakeSuppressDuration = Duration(seconds: 3);
  String? _lastRouteDebugKey;
  late final SessionLogger _sessionLogger = SessionLogger(() => token != null ? api : null);
  String? _lastExportSessionId;
  String? lastCalendarSyncStatus;
  String? lastLocationSyncStatus;
  DateTime? lastCalendarSyncAt;
  DateTime? lastLocationSyncAt;

  ApiClient get api => ApiClient(token);

  String? get lastExportSessionId => _lastExportSessionId;

  /// True while a bounded voice conversation session is open (multi-turn until idle timeout).
  bool get inConversation => _inConversation;

  void _agentDebug(String hypothesisId, String location, String message, [Map<String, dynamic>? data]) {
    if (token == null) return;
    unawaited(
      api.agentDebugLog(
        hypothesisId: hypothesisId,
        location: location,
        message: message,
        data: data ?? {},
      ),
    );
  }

  bool get _isAndroid =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  String get _wakeName =>
      profile?['wake_name'] as String? ?? profile?['display_name'] as String? ?? 'friend';

  /// The user's selected Companion voice ID (from voice catalogue). Defaults to "aria".
  String get companionVoiceId => profile?['tts_voice'] as String? ?? 'aria';
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
    _foregroundDebounce?.cancel();
    _foregroundDebounce = null;
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
          unawaited(_syncDeviceLocation(silent: true));
          await _loadCheckinBanner();
          await refreshTodayView();
          _startDateCheckTimer();
        } catch (_) {
          token = null;
          profile = null;
        }
      }
      await _loadWakePrefs();
      WakeWordEngine.agentDebug = (hypothesisId, message, data) =>
          _agentDebug(hypothesisId, 'wake_word_engine', message, data);
      try {
        await syncWakeListener();
      } catch (_) {}
    } finally {
      notifyListeners();
    }
  }

  void _startDateCheckTimer() {
    _dateCheckTimer?.cancel();
    _dateCheckTimer = Timer.periodic(const Duration(minutes: 5), (_) {
      if (token != null) unawaited(refreshTodayViewIfDateChanged());
    });
  }

  Future<void> _loadWakePrefs() async {
    wakeWordEnabled = await WakeWordPrefs.isEnabled();
    _calibratedWakeThreshold = await WakeWordPrefs.getCalibratedThreshold();
  }

  double? _calibratedWakeThreshold;

  Future<void> refreshWakeCalibration() async {
    await _loadWakePrefs();
    await _stopWakeListener();
    await syncWakeListener();
    notifyListeners();
  }

  Future<void> pauseWakeForCalibration() async {
    _wakePausedForCalibration = true;
    _wakeRetryTimer?.cancel();
    _wakeRetryAttempts = 0;
    _activeWakeRoute = null;
    wakeWordListening = false;
    wakeWordError = null;
    await _stopAllWakeListening();
    notifyListeners();
  }

  Future<void> resumeWakeAfterCalibration() async {
    _wakePausedForCalibration = false;
    await _loadWakePrefs();
    await syncWakeListener();
    notifyListeners();
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

  Future<void> _syncDeviceLocation({bool silent = false}) async {
    try {
      final loc = await DeviceLocation.getCityAndCountry();
      if (loc == null) {
        lastLocationSyncStatus =
            'Location unavailable (permission denied, service off, or city could not be resolved).';
        if (!silent) notifyListeners();
        return;
      }
      final profileCity = profile?['city'] as String?;
      if (loc.city != profileCity) {
        profile = await api.updateProfile({'city': loc.city, 'country_code': loc.countryCode});
      }
      lastLocationSyncAt = DateTime.now();
      lastLocationSyncStatus = 'Detected ${loc.city}, ${loc.countryCode}';
      if (!silent) notifyListeners();
    } catch (e) {
      lastLocationSyncStatus = 'Location sync failed: $e';
      if (!silent) notifyListeners();
    }
  }

  Future<void> syncDeviceLocationNow() async {
    if (token == null || kIsWeb) return;
    await _syncDeviceLocation();
  }

  Future<void> setWakeWordEnabled(bool enabled) async {
    wakeWordEnabled = enabled;
    if (!enabled) {
      wakeWordError = null;
      wakeWordListening = false;
      _activeWakeRoute = null;
      _wakeSuppressResyncTimer?.cancel();
      _wakeSuppressResyncTimer = null;
    }
    _foregroundDebounce?.cancel();
    _foregroundDebounce = null;
    notifyListeners();
    await WakeWordPrefs.setEnabled(enabled);
    if (enabled) _armWakeSuppress();
    await syncWakeListener();
    notifyListeners();
  }

  void updateLifecycle(AppLifecycleState state) {
    _lifecycle = state;
    if (state == AppLifecycleState.resumed) {
      setAppForeground(true);
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.detached) {
      setAppForeground(false);
    }
  }

  /// Stabilization mode: Android wake stays on FGS-only to avoid dual-engine races.
  bool _useForegroundWakeRoute() =>
      !_isAndroid && (_lifecycle == AppLifecycleState.resumed || _appInForeground);

  void _armWakeSuppress([Duration? duration]) {
    final d = duration ?? _wakeSuppressDuration;
    _wakeSuppressUntil = DateTime.now().add(d);
    _wakeSuppressResyncTimer?.cancel();
    _wakeSuppressResyncTimer = Timer(d + const Duration(milliseconds: 100), () {
      if (wakeWordEnabled && token != null) {
        unawaited(syncWakeListener());
      }
    });
    _agentDebug('H4', 'app_state._armWakeSuppress', 'armed', {
      'untilMs': _wakeSuppressUntil!.millisecondsSinceEpoch,
    });
  }

  void setAppForeground(bool inForeground) {
    if (inForeground) {
      _foregroundDebounce?.cancel();
      _foregroundDebounce = null;
      if (_appInForeground) return;
      _appInForeground = true;
      unawaited(syncWakeListener());
      return;
    }
    if (!_appInForeground) return;
    _foregroundDebounce?.cancel();
    _foregroundDebounce = Timer(const Duration(milliseconds: 800), () {
      _foregroundDebounce = null;
      if (_lifecycle == AppLifecycleState.resumed) {
        _agentDebug('H2', 'app_state.setAppForeground', 'background_debounce_skipped', {
          'lifecycle': _lifecycle.name,
        });
        return;
      }
      if (!_appInForeground) return;
      _appInForeground = false;
      _agentDebug('H2', 'app_state.setAppForeground', 'background_applied', {
        'lifecycle': _lifecycle.name,
      });
      unawaited(syncWakeListener());
    });
  }

  Future<void> syncWakeListener() async {
    if (_lifecycle == AppLifecycleState.resumed) {
      _foregroundDebounce?.cancel();
      _foregroundDebounce = null;
    }
    _syncWakeDebounce?.cancel();
    final completer = Completer<void>();
    _syncWakeDebounce = Timer(const Duration(milliseconds: 300), () {
      final job = _syncWakeChain.then((_) => _syncWakeListenerImplBody());
      _syncWakeChain = job.catchError((_) {});
      job.whenComplete(() {
        if (!completer.isCompleted) completer.complete();
      });
    });
    return completer.future;
  }

  Future<void> _syncWakeListenerImplBody() async {
    if (!wakeWordAvailable || token == null) {
      await _stopAllWakeListening();
      notifyListeners();
      return;
    }
    if (_wakePausedForCalibration) {
      await _stopAllWakeListening();
      wakeWordListening = false;
      wakeWordError = null;
      notifyListeners();
      return;
    }

    if (_isAndroid) {
      await _syncAndroidBackgroundWake();
      return;
    }

    final shouldListen = wakeWordEnabled &&
        selectedTab == 0 &&
        !_inConversation &&
        !_blocksWakeListener();
    if (!shouldListen) {
      await _stopWakeListener();
      wakeWordListening = false;
      notifyListeners();
      return;
    }
    _wakeWord ??= WakeWordService(
      onWake: () => unawaited(_onWakeWordDetected()),
      shouldSuppress: _blocksWakeFire,
      calibratedThreshold: _calibratedWakeThreshold,
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
    if (!wakeWordEnabled) {
      _activeWakeRoute = null;
      _wakeRetryTimer?.cancel();
      _wakeRetryAttempts = 0;
      await _stopWakeListener();
      await WakeBackgroundService.stop();
      wakeWordListening = false;
      notifyListeners();
      return;
    }

    final suppressed = _inConversation || _blocksWakeListener();
    final routeKey =
        '${_useForegroundWakeRoute()}|$_lifecycle|$_appInForeground|$selectedTab|$suppressed|$_activeWakeRoute|${_wakeWord?.isListening}';
    if (routeKey != _lastRouteDebugKey) {
      _lastRouteDebugKey = routeKey;
      _agentDebug('H2', 'app_state._syncAndroidBackgroundWake', 'route_decision', {
        'foreground': _appInForeground,
        'lifecycle': _lifecycle.name,
        'useForegroundRoute': _useForegroundWakeRoute(),
        'tab': selectedTab,
        'suppressed': suppressed,
        'activeRoute': _activeWakeRoute,
        'listening': _wakeWord?.isListening ?? false,
      });
    }

    if (suppressed) {
      _activeWakeRoute = null;
      await _stopWakeListener();
      if (await WakeBackgroundService.isRunning()) {
        WakeBackgroundService.setSuppressed(true);
      }
      wakeWordListening = false;
      notifyListeners();
      return;
    }

    // App visible: in-process OpenWakeWord (build 55 path — no platform STT).
    if (_useForegroundWakeRoute()) {
      if (_activeWakeRoute == 'fgs') {
        await WakeBackgroundService.stop();
        await Future<void>.delayed(const Duration(milliseconds: 300));
        _activeWakeRoute = null;
      }
      if (_activeWakeRoute == 'foreground' && _wakeWord != null) {
        if (!_wakeWord!.isListening) {
          await _wakeWord!.start();
        }
        wakeWordListening = _wakeWord!.isListening;
        wakeWordError = wakeWordListening ? null : wakeWordError;
        notifyListeners();
        return;
      }
      if (await WakeBackgroundService.isRunning()) {
        await WakeBackgroundService.stop();
        await Future<void>.delayed(const Duration(milliseconds: 500));
      }
      _wakeWord ??= WakeWordService(
        onWake: () => unawaited(_onWakeWordDetected()),
        shouldSuppress: _blocksWakeFire,
        calibratedThreshold: _calibratedWakeThreshold,
      );
      if (!await _wakeWord!.init()) {
        _activeWakeRoute = null;
        wakeWordListening = false;
        wakeWordError = WakeWordEngine.lastInitError ?? 'Wake word engine failed to start.';
        _agentDebug('H1', 'app_state.foreground_wake', 'init_failed', {
          'error': wakeWordError,
        });
      } else {
        await _wakeWord!.start();
        wakeWordListening = _wakeWord!.isListening;
        wakeWordError = wakeWordListening
            ? null
            : (WakeWordEngine.lastInitError ?? 'Mic not available for Hi Pal.');
        _activeWakeRoute = wakeWordListening ? 'foreground' : null;
        _agentDebug('H1', 'app_state.foreground_wake', 'started', {
          'listening': wakeWordListening,
          'error': wakeWordError,
        });
      }
      notifyListeners();
      return;
    }

    _activeWakeRoute = 'fgs';
    await _stopWakeListener();
    final running = await WakeBackgroundService.ensureRunning();
    if (running) {
      _wakeRetryTimer?.cancel();
      _wakeRetryAttempts = 0;
      WakeBackgroundService.setSuppressed(suppressed);
      _agentDebug('H1', 'app_state._syncAndroidBackgroundWake', 'fgs_sync', {
        'suppressed': suppressed,
        'running': running,
      });
      if (suppressed) {
        wakeWordListening = false;
      } else {
        wakeWordError = null;
        _wakeEngineReadyCompleter = Completer<void>();
        WakeBackgroundService.ensureListening();
        final ready = await _awaitWakeEngineReady(timeout: const Duration(seconds: 8));
        if (!ready) {
          wakeWordListening = false;
          wakeWordError =
              'Wake listener did not start. Check microphone and notification permissions, then retry.';
        }
      }
    } else {
      wakeWordListening = false;
      wakeWordError = 'Microphone or notification permission required for Hi Pal.';
      if (wakeWordEnabled && !_wakePausedForCalibration && _wakeRetryAttempts < 2) {
        _wakeRetryAttempts += 1;
        _wakeRetryTimer?.cancel();
        _wakeRetryTimer = Timer(Duration(seconds: 2 * _wakeRetryAttempts), () {
          if (wakeWordEnabled && !_wakePausedForCalibration) {
            unawaited(syncWakeListener());
          }
        });
      }
    }
    notifyListeners();
  }

  Future<void> _stopWakeListener() async {
    await _wakeWord?.stop();
  }

  Future<void> _stopAllWakeListening() async {
    await _stopWakeListener();
    if (_isAndroid) {
      await WakeBackgroundService.stop();
    }
    wakeWordListening = false;
  }

  void _onBackgroundWakeData(Object data) {
    if (data is! Map) return;
    final event = data['event'];
    if (event == 'wake') {
      _agentDebug('H1', 'app_state._onBackgroundWakeData', 'wake_event_received', {
        'inConversation': _inConversation,
        'loopActive': _voiceLoop?.isActive ?? false,
      });
      unawaited(handleBackgroundWake());
    } else if (event == 'engine_ready') {
      _wakeEngineReadyCompleter?.complete();
      wakeWordListening =
          wakeWordEnabled && !_inConversation && !_blocksWakeListener();
      wakeWordError = null;
      _agentDebug('H1', 'app_state._onBackgroundWakeData', 'engine_ready', {
        'wakeWordListening': wakeWordListening,
      });
      notifyListeners();
    } else if (event == 'engine_failed') {
      wakeWordListening = false;
      wakeWordError = data['error'] as String? ?? 'Wake word engine failed to start.';
      _agentDebug('H1', 'app_state._onBackgroundWakeData', 'engine_failed', {
        'error': wakeWordError,
      });
      notifyListeners();
    }
  }

  Future<void> handleBackgroundWake() async {
    if (_wakePausedForCalibration) return;
    if (_inConversation && _voiceLoop?.isActive == true) return;
    if (_inConversation && (_voiceLoop == null || !_voiceLoop!.isActive)) {
      await _endConversation();
    }
    if (_inConversation) return;
    selectedTab = 0;
    WakeBackgroundService.setSuppressed(true);
    notifyListeners();
    await _startConversation();
  }

  Future<void> _onWakeWordDetected() async {
    if (_blocksWakeFire()) {
      _agentDebug('H4', 'app_state._onWakeWordDetected', 'wake_suppressed', {
        'inConversation': _inConversation,
        'foreground': _appInForeground,
        'lifecycle': _lifecycle.name,
      });
      return;
    }
    _agentDebug('H1', 'app_state._onWakeWordDetected', 'wake_detected', {
      'inConversation': _inConversation,
      'foreground': _appInForeground,
      'tab': selectedTab,
    });
    if (_inConversation && _voiceLoop?.isActive == true) return;
    if (_inConversation && (_voiceLoop == null || !_voiceLoop!.isActive)) {
      await _endConversation();
    }
    if (_inConversation) return;
    await _stopWakeListener();
    await _startConversation();
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

  Future<void> setTokenFromSocialAuth(Map<String, dynamic> authResponse) async {
    final t = authResponse['access_token'] as String?;
    if (t == null) throw Exception('No token in auth response');
    token = t;
    await _storage.write(key: 'token', value: token);
    profile = await api.getProfile();
    await _loadCheckinBanner();
    await refreshTodayView();
    _startDateCheckTimer();
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
        final count = await api.importCalendar(events);
        lastCalendarSyncAt = DateTime.now();
        lastCalendarSyncStatus = 'Synced $count event(s)';
      } else {
        lastCalendarSyncStatus = 'No events found for today';
      }
    } catch (e) {
      lastCalendarSyncStatus = 'Calendar sync failed: $e';
    }
    notifyListeners();
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

  /// Refreshes Today view only when the stored date differs from today's local date.
  /// Safe to call on every app resume — no-ops if already fresh.
  Future<void> refreshTodayViewIfDateChanged() async {
    if (token == null) return;
    final storedDate = todayView?['summary']?['date'] as String?;
    final todayDate = DateTime.now().toLocal();
    final todayStr =
        '${todayDate.year}-${todayDate.month.toString().padLeft(2, '0')}-${todayDate.day.toString().padLeft(2, '0')}';
    if (storedDate == null || storedDate != todayStr) {
      await refreshTodayView();
    }
  }

  Timer? _dateCheckTimer;

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
    if (_speaking || _processingTurn || _inConversation) return;
    if (selectedTab != 0) return;
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

  bool _blocksWakeListener() =>
      _inConversation || _speaking || _processingTurn;

  bool _blocksWakeFire() {
    if (_blocksWakeListener()) return true;
    final until = _wakeSuppressUntil;
    return until != null && DateTime.now().isBefore(until);
  }

  static bool _isEndConversationIntent(String? text) {
    if (text == null || text.trim().isEmpty) return false;
    final t = text.toLowerCase().trim();
    return RegExp(
      r"^(bye|goodbye|that's all|thats all|stop listening|end conversation|thanks,? that's all)\b",
    ).hasMatch(t);
  }

  void _cancelConversationIdleTimer() {
    _conversationIdleTimer?.cancel();
    _conversationIdleTimer = null;
  }

  void _armConversationIdleTimer() {
    if (!_inConversation) return;
    _cancelConversationIdleTimer();
    _conversationIdleTimer = Timer(
      const Duration(seconds: _conversationIdleSeconds),
      () => unawaited(_endConversation()),
    );
  }

  DateTime? _lastToggleLiveAt;

  Future<void> toggleLive() async {
    if (token == null || _toggleLiveInProgress) return;
    // Gate 6: 300ms debounce — prevent rapid double-tap reopening a session.
    final now = DateTime.now();
    if (_lastToggleLiveAt != null &&
        now.difference(_lastToggleLiveAt!) < const Duration(milliseconds: 300)) {
      return;
    }
    _lastToggleLiveAt = now;
    _toggleLiveInProgress = true;
    try {
      final liveActive = _inConversation ||
          liveSession.isActive ||
          (_voiceLoop?.isActive ?? false);
      if (liveActive) {
        _turnGeneration++;
        _processingTurn = false;
        _speaking = false;
        _awaitingGreeting = false;
        await _player.stop();
        _armWakeSuppress();
        await _endConversation();
      } else {
        await _startConversation();
      }
      notifyListeners();
    } finally {
      _toggleLiveInProgress = false;
    }
  }

  Future<void> _startConversation() async {
    if (_inConversation) return;
    if (_isAndroid && wakeWordEnabled) {
      WakeBackgroundService.setSuppressed(true);
    } else {
      await _stopWakeListener();
    }
    final loop = LiveVoiceLoop(
      onSegment: _handleVoiceSegment,
      onSegmentRejected: () => unawaited(_onSegmentRejected()),
      shouldSuppress: () => _speaking || _awaitingGreeting || _processingTurn,
      isSpeakingForVad: _isSpeakingForVad,
      thresholdDb: -45.0,
      thresholdDbSpeaking: -32.0,
      onSpeechStart: () {
        _armConversationIdleTimer();
        if (_speaking) {
          _turnGeneration++;
          _speaking = false;
          if (_inConversation) {
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
      _inConversation = true;
      _consecutiveDiscards = 0;
      _consecutiveTurnTimeouts = 0;
      _softPromptShown = false;
      _lastDiscardAt = null;
      await liveSession.start(token!, (msg) {
        if (msg['type'] == 'reply') {
          lastReply = msg['text'] as String?;
          notifyListeners();
        }
      });
      _awaitingGreeting = true;
      notifyListeners();
      await _playLiveGreeting();
      _awaitingGreeting = false;
      if (!_inConversation) return;
      _voiceLoop = loop;
      await loop.start();
      liveSession.state = LiveState.listening;
      _armConversationIdleTimer();
      notifyListeners();
    } catch (e) {
      lastReply = e.toString();
      await _endConversation();
    }
  }

  Future<void> _onSegmentRejected() async {
    if (!_inConversation) return;
    final now = DateTime.now();
    if (_lastDiscardAt != null &&
        now.difference(_lastDiscardAt!) > const Duration(seconds: 10)) {
      _consecutiveDiscards = 0;
    }
    _lastDiscardAt = now;
    _consecutiveDiscards++;
    _armConversationIdleTimer();
    if (_consecutiveDiscards >= 6) {
      await _endConversation();
      return;
    }
    if (_consecutiveDiscards >= 2 && !_speaking && !_processingTurn && !_softPromptShown) {
      _softPromptShown = true;
      lastReply = "I'm listening — go ahead.";
      notifyListeners();
    } else {
      notifyListeners();
    }
  }

  Future<void> _stopVoiceLoop() async {
    final loop = _voiceLoop;
    _voiceLoop = null;
    if (loop != null) {
      await loop.stop();
      await loop.dispose();
    }
  }

  Future<void> _endConversation() async {
    _cancelConversationIdleTimer();
    _turnGeneration++;
    _armWakeSuppress();
    _inConversation = false;
    _awaitingGreeting = false;
    _consecutiveDiscards = 0;
    _consecutiveTurnTimeouts = 0;
    _softPromptShown = false;
    await _stopVoiceLoop();
    await liveSession.stop();
    _speaking = false;
    _processingTurn = false;
    liveSession.state = LiveState.resting;
    lastReply = null;
    lastTranscript = null;
    await _restartWakeAfterLive();
    notifyListeners();
  }

  Future<void> _returnToListening() async {
    if (!_inConversation) return;
    liveSession.state = LiveState.listening;
    final loop = _voiceLoop;
    if (loop != null && !loop.isActive) {
      await loop.start();
    }
    _armConversationIdleTimer();
    notifyListeners();
  }

  Future<bool> _awaitWakeEngineReady({Duration timeout = const Duration(seconds: 5)}) async {
    final completer = _wakeEngineReadyCompleter;
    if (completer == null) return false;
    try {
      await completer.future.timeout(timeout);
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> _restartWakeAfterLive() async {
    if (!wakeWordEnabled) return;
    if (_isAndroid) {
      WakeBackgroundService.setSuppressed(false);
      await WakeBackgroundService.stop();
      await _stopWakeListener();
      await Future<void>.delayed(const Duration(milliseconds: 800));
    }
    await syncWakeListener();
  }

  static bool _isNoiseClassReply(String? reply) {
    if (reply == null || reply.isEmpty) return false;
    final lower = reply.toLowerCase();
    return lower.contains('did not catch') || lower.contains('did not receive any audio');
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
      if (text == null || text.isEmpty || !_inConversation) return;
      lastReply = text;
      notifyListeners();
      if (!_inConversation) return;
      final tts = await api.tts(text);
      if (!_inConversation) return;
      await _playAudioResponse(tts);
    } catch (_) {}
  }

  Future<void> _handleVoiceSegment(List<int> bytes) async {
    if (token == null || _processingTurn || !_inConversation) return;
    _cancelConversationIdleTimer();
    final turnGen = ++_turnGeneration;
    _processingTurn = true;
    liveSession.state = LiveState.thinking;
    notifyListeners();
    var shouldRefreshToday = false;
    var endAfterTurn = false;
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
      await _applyMusicCommand(res);
      lastTranscript = res['transcript'] as String?;
      lastReply = res['reply'] as String?;
      if (_isEndConversationIntent(lastTranscript)) {
        endAfterTurn = true;
      }
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
      _consecutiveDiscards = 0;
      _consecutiveTurnTimeouts = 0;
      final skipTts = res['skip_tts'] == true;
      final transcript = (res['transcript'] as String?) ?? '';
      if (skipTts || (transcript.isEmpty && _isNoiseClassReply(res['reply'] as String?))) {
        if (transcript.isEmpty) {
          lastReply = null;
        }
      } else {
        await _playAudioResponse(res, turnGen: turnGen);
      }
    } catch (e) {
      if (turnGen == _turnGeneration) {
        final isTimeout = e is TimeoutException ||
            e.toString().contains('TimeoutException');
        if (isTimeout) {
          _consecutiveTurnTimeouts++;
          lastReply = _consecutiveTurnTimeouts >= 2
              ? "That took too long — ending Live. Tap the orb or say Hi Pal to try again."
              : "That took too long — still listening.";
        } else {
          _consecutiveTurnTimeouts = 0;
          lastReply = 'Something went wrong with that turn. Still listening.';
        }
      }
    } finally {
      _processingTurn = false;
      if (_inConversation) {
        if (endAfterTurn || _consecutiveTurnTimeouts >= 2) {
          if (_consecutiveTurnTimeouts >= 2) {
            _consecutiveTurnTimeouts = 0;
          }
          await _endConversation();
        } else {
          await _returnToListening();
        }
        notifyListeners();
        if (shouldRefreshToday) {
          unawaited(refreshTodayView());
        }
      } else {
        notifyListeners();
        if (shouldRefreshToday) {
          unawaited(refreshTodayView());
        }
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
    notifyListeners();
  }

  @override
  void dispose() {
    _cancelConversationIdleTimer();
    _cancelNudgeTimers();
    _dateCheckTimer?.cancel();
    _foregroundDebounce?.cancel();
    _wakeSuppressResyncTimer?.cancel();
    _wakeRetryTimer?.cancel();
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
    await _applyMusicCommand(res);
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

  Future<void> _applyMusicCommand(Map<String, dynamic> res) async {
    if (!_isAndroid) return;
    final command = res['music_command'];
    if (command is! Map) return;
    final launched = await MusicCommandService.launchSpotify(Map<String, dynamic>.from(command));
    if (!launched) {
      final action = (command['action'] as String? ?? 'play').toLowerCase();
      if (action == 'play') {
        lastReply = "I couldn't open Spotify on this device. Install Spotify and try again.";
      }
    }
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
