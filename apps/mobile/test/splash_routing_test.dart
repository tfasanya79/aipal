import 'package:aipal/providers/app_state.dart';
import 'package:aipal/screens/home_shell.dart';
import 'package:aipal/screens/onboarding_screen.dart';
import 'package:aipal/screens/splash_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

Widget _wrap(AppState state) {
  return ChangeNotifierProvider.value(
    value: state,
    child: const MaterialApp(home: SplashScreen()),
  );
}

void main() {
  testWidgets('shows spinner while auth not ready', (tester) async {
    final state = AppState();
    await tester.pumpWidget(_wrap(state));
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Email for magic link'), findsNothing);
  });

  testWidgets('routes to email onboarding when token null', (tester) async {
    final state = AppState()..authReady = true;
    await tester.pumpWidget(_wrap(state));
    await tester.pump();
    expect(find.text('Email for magic link'), findsOneWidget);
    expect(find.byType(OnboardingScreen), findsOneWidget);
  });

  testWidgets('routes to profile step when token without names', (tester) async {
    final state = AppState()
      ..authReady = true
      ..token = 'fake-token'
      ..profile = {'email': 'user@example.com'};
    await tester.pumpWidget(_wrap(state));
    await tester.pump();
    expect(find.text('What should I call you?'), findsOneWidget);
    expect(find.text('Email for magic link'), findsNothing);
  });

  testWidgets('routes to home when profile complete', (tester) async {
    final state = AppState()
      ..authReady = true
      ..token = 'fake-token'
      ..profile = {'wake_name': 'Alex', 'display_name': 'Alex'};
    await tester.pumpWidget(_wrap(state));
    await tester.pump();
    expect(find.byType(HomeShell), findsOneWidget);
    expect(find.text('Companion'), findsOneWidget);
  });
}
