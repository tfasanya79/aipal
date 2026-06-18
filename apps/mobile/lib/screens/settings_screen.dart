import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../providers/app_state.dart';
import '../services/calendar_service.dart';
import '../services/notification_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _recordSessions = true;
  final _phaseController = TextEditingController();
  bool _loaded = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadPrefs());
  }

  Future<void> _loadPrefs() async {
    final state = context.read<AppState>();
    final enabled = await state.sessionRecordingEnabled();
    final tag = await state.sessionPhaseTag();
    if (!mounted) return;
    setState(() {
      _recordSessions = enabled;
      _phaseController.text = tag ?? '';
      _loaded = true;
    });
  }

  @override
  void dispose() {
    _phaseController.dispose();
    super.dispose();
  }

  Future<void> _exportSession(BuildContext context) async {
    final state = context.read<AppState>();
    try {
      final data = await state.exportLastSession();
      if (!context.mounted) return;
      if (data == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No session to export yet — try a Live or text turn first.')),
        );
        return;
      }
      final json = const JsonEncoder.withIndent('  ').convert(data);
      await Clipboard.setData(ClipboardData(text: json));
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Session log copied to clipboard')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Export failed: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final p = state.profile;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        ListTile(
          title: const Text('Profile'),
          subtitle: Text(p?['email']?.toString() ?? ''),
        ),
        ListTile(
          title: const Text('Wake name'),
          subtitle: Text(p?['wake_name']?.toString() ?? '—'),
        ),
        SwitchListTile(
          title: const Text('Listen for Hi Pal'),
          subtitle: kIsWeb
              ? const Text('Wake word is available on the Android app.')
              : defaultTargetPlatform == TargetPlatform.android
                  ? const Text(
                      'Say Hi Pal anytime to start Live. Shows a listening notification while enabled. Background listening uses more battery.',
                    )
                  : const Text(
                      'On the Companion tab, say Hi Pal to start Live hands-free.',
                    ),
          value: state.wakeWordEnabled,
          onChanged: kIsWeb ? null : (v) => state.setWakeWordEnabled(v),
        ),
        SwitchListTile(
          title: const Text('Check-in enabled'),
          value: p?['checkin_enabled'] as bool? ?? true,
          onChanged: (v) => state.updateProfile({'checkin_enabled': v}),
        ),
        const Divider(),
        const ListTile(
          title: Text('Test session logging'),
          subtitle: Text('Record events while you test each build. Export and share for debugging.'),
        ),
        if (_loaded)
          SwitchListTile(
            title: const Text('Record test sessions'),
            value: _recordSessions,
            onChanged: (v) async {
              setState(() => _recordSessions = v);
              await state.setSessionRecordingEnabled(v);
            },
          ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: TextField(
            controller: _phaseController,
            decoration: const InputDecoration(
              labelText: 'Phase tag (optional)',
              hintText: 'e.g. build-39-voice',
              border: OutlineInputBorder(),
            ),
            onSubmitted: (v) => state.setSessionPhaseTag(v),
            onEditingComplete: () => state.setSessionPhaseTag(_phaseController.text),
          ),
        ),
        ListTile(
          title: const Text('Export last session'),
          subtitle: Text(
            state.lastExportSessionId != null
                ? 'Session ${state.lastExportSessionId}'
                : 'No session yet',
          ),
          trailing: const Icon(Icons.copy),
          onTap: () => _exportSession(context),
        ),
        const Divider(),
        ListTile(
          title: const Text('Reschedule morning brief'),
          onTap: () => NotificationService.instance.scheduleMorningBrief(hour: 8, minute: 0),
        ),
        ListTile(
          title: const Text('Import today\'s calendar (v2.1)'),
          onTap: () async {
            final events = await CalendarService().fetchTodayEvents();
            if (context.mounted && events.isNotEmpty) {
              final n = await context.read<AppState>().api.importCalendar(events);
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('Imported $n calendar events')),
                );
              }
            }
          },
        ),
        ListTile(
          title: const Text('Connect Spotify (v2.1)'),
          subtitle: const Text('Opens when server OAuth is configured'),
          onTap: () async {
            final uri = Uri.parse('https://43.160.220.9.sslip.io/privacy-policy.html');
            await launchUrl(uri);
          },
        ),
        const Divider(),
        FutureBuilder<PackageInfo>(
          future: PackageInfo.fromPlatform(),
          builder: (context, snapshot) {
            final info = snapshot.data;
            return ListTile(
              title: const Text('App version'),
              subtitle: Text(
                info != null ? '${info.version} (build ${info.buildNumber})' : 'Loading…',
              ),
            );
          },
        ),
        const Padding(
          padding: EdgeInsets.all(8),
          child: Text(
            'AiPal is a supportive companion, not medical advice.',
            style: TextStyle(fontSize: 12),
          ),
        ),
      ],
    );
  }
}
