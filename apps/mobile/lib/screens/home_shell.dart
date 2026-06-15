import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import 'companion_screen.dart';
import 'settings_screen.dart';
import 'today_screen.dart';

class HomeShell extends StatelessWidget {
  const HomeShell({super.key});

  static const _tabs = [
    CompanionScreen(),
    TodayScreen(),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    final index = context.watch<AppState>().selectedTab;
    return Scaffold(
      body: _tabs[index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (i) => context.read<AppState>().goToTab(i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.circle_outlined), label: 'Companion'),
          NavigationDestination(icon: Icon(Icons.checklist), label: 'Today'),
          NavigationDestination(icon: Icon(Icons.settings), label: 'Settings'),
        ],
      ),
    );
  }
}
