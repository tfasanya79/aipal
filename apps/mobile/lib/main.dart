import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import 'providers/app_state.dart';
import 'screens/splash_screen.dart';
import 'services/notification_service.dart';
import 'services/wake_background_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Global error handlers — prevent silent crashes from killing the process.
  FlutterError.onError = (FlutterErrorDetails details) {
    FlutterError.presentError(details);
    debugPrint('[AiPal] FlutterError: ${details.exceptionAsString()}');
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    debugPrint('[AiPal] PlatformDispatcher error: $error\n$stack');
    return true; // handled — do not propagate
  };

  if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
    FlutterForegroundTask.initCommunicationPort();
    try {
      await WakeBackgroundService.init();
    } catch (e) {
      debugPrint('[AiPal] WakeBackgroundService.init failed: $e');
    }
  }
  final appState = AppState();
  try {
    await NotificationService.instance.init(
      onForegroundNudge: (taskId, minutes) =>
          appState.handleForegroundNudge(taskId, minutes),
    );
  } catch (_) {
    // Notifications optional — must not block app launch (APK sideload / web).
  }
  await appState.loadStoredAuth();
  runApp(AipalApp(appState: appState));
  WidgetsBinding.instance.addPostFrameCallback((_) {
    unawaited(appState.finishBootstrap());
  });
}

class AipalApp extends StatefulWidget {
  const AipalApp({super.key, required this.appState});

  final AppState appState;

  @override
  State<AipalApp> createState() => _AipalAppState();
}

class _AipalAppState extends State<AipalApp> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    widget.appState.updateLifecycle(state);
    // inactive = still visible (keyboard, system UI); only paused/hidden = background.
    if (state == AppLifecycleState.resumed) {
      unawaited(widget.appState.syncDeviceCalendar());
      unawaited(widget.appState.syncWakeListener());
      unawaited(widget.appState.refreshTodayViewIfDateChanged());
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = MaterialApp(
      title: 'AiPal',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0D1117),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFE8A838),
          secondary: Color(0xFF9B7EDE),
          surface: Color(0xFF161B22),
        ),
        textTheme: GoogleFonts.nunitoTextTheme(ThemeData.dark().textTheme),
      ),
      home: const SplashScreen(),
    );
    return ChangeNotifierProvider.value(
      value: widget.appState,
      child: (!kIsWeb && defaultTargetPlatform == TargetPlatform.android)
          ? WithForegroundTask(child: app)
          : app,
    );
  }
}
