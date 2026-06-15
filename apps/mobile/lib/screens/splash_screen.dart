import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';
import 'onboarding_screen.dart';

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, state, _) {
        if (state.token == null) {
          return const OnboardingScreen();
        }
        if (state.profile?['wake_name'] == null && state.profile?['display_name'] == null) {
          return const OnboardingScreen(continueProfile: true);
        }
        return const HomeShell();
      },
    );
  }
}
