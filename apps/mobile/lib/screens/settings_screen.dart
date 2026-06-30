import 'dart:convert';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../providers/app_state.dart';
import '../screens/wake_enrollment_screen.dart';
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
  final _previewPlayer = AudioPlayer();
  bool _previewLoading = false;
  bool _weeklySummarySending = false;
  Map<String, dynamic>? _weeklySummaryPreview;

  static const _voiceCatalogue = [
    {'id': 'aria', 'name': 'Aria (default)', 'gender': 'Female', 'style': 'Warm, clear'},
    {'id': 'jenny', 'name': 'Jenny', 'gender': 'Female', 'style': 'Bright, friendly'},
    {'id': 'emma', 'name': 'Emma', 'gender': 'Female', 'style': 'Calm, natural'},
    {'id': 'andrew', 'name': 'Andrew', 'gender': 'Male', 'style': 'Deep, calm'},
    {'id': 'brian', 'name': 'Brian', 'gender': 'Male', 'style': 'Warm, steady'},
    {'id': 'sonia', 'name': 'Sonia (British)', 'gender': 'Female', 'style': 'Clear, British'},
  ];

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
    _previewPlayer.dispose();
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

  Future<void> _playVoicePreview(AppState state, String voiceId) async {
    if (_previewLoading) return;
    setState(() => _previewLoading = true);
    try {
      final bytes = await state.api.voicePreview(voiceId);
      await _previewPlayer.stop();
      await _previewPlayer.play(BytesSource(Uint8List.fromList(bytes)));
    } catch (_) {
      // ignore preview errors silently
    } finally {
      if (mounted) setState(() => _previewLoading = false);
    }
  }

  void _openVoicePicker(BuildContext context, AppState state) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF161B22),
      builder: (_) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Choose Companion voice',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            ..._voiceCatalogue.map((v) {
              final id = v['id'] as String;
              final isSelected = state.companionVoiceId == id;
              return Card(
                color: isSelected
                    ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.15)
                    : const Color(0xFF21262D),
                child: ListTile(
                  leading: Icon(
                    v['gender'] == 'Male' ? Icons.person : Icons.person_2,
                    color: isSelected
                        ? Theme.of(context).colorScheme.primary
                        : Colors.white54,
                  ),
                  title: Text(v['name'] as String),
                  subtitle: Text('${v['gender']} · ${v['style']}'),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        icon: _previewLoading
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.play_circle_outline, size: 22),
                        onPressed: () => _playVoicePreview(state, id),
                        tooltip: 'Preview',
                      ),
                      if (isSelected)
                        Icon(Icons.check_circle, color: Theme.of(context).colorScheme.primary),
                    ],
                  ),
                  onTap: () async {
                    Navigator.pop(context);
                    await state.updateProfile({'tts_voice': id});
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('Companion voice set to ${v['name']}')),
                      );
                    }
                  },
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  Future<void> _previewAndSendWeeklySummary(BuildContext context, AppState state) async {
    setState(() => _weeklySummaryPreview = null);
    try {
      final summary = await state.api.getWeeklySummary();
      if (!context.mounted) return;
      setState(() => _weeklySummaryPreview = summary);
      final note = summary['companion_note'] as String? ?? '';
      final completed = summary['tasks_completed'] as int? ?? 0;
      final streak = summary['streak_days'] as int? ?? 0;
      showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: const Color(0xFF161B22),
        builder: (ctx) => Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 36),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Weekly Summary Preview',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              Text('Tasks completed: $completed'),
              Text('Streak: $streak days'),
              if (note.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(note, style: const TextStyle(fontStyle: FontStyle.italic, color: Colors.white70)),
              ],
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  icon: _weeklySummarySending
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.send),
                  label: const Text('Send to my email'),
                  onPressed: _weeklySummarySending
                      ? null
                      : () async {
                          setState(() => _weeklySummarySending = true);
                          try {
                            final sent = await state.api.sendWeeklySummary();
                            if (ctx.mounted) {
                              Navigator.pop(ctx);
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(content: Text(sent ? 'Summary sent! Check your inbox.' : 'Send failed — try again.')),
                              );
                            }
                          } finally {
                            if (mounted) setState(() => _weeklySummarySending = false);
                          }
                        },
                ),
              ),
            ],
          ),
        ),
      );
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not load summary: $e')),
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
        if (state.wakeWordError != null && state.wakeWordEnabled)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Text(
              state.wakeWordError!,
              style: TextStyle(fontSize: 13, color: Theme.of(context).colorScheme.error),
            ),
          ),
        if (!kIsWeb)
          ListTile(
            title: const Text('Calibrate wake phrase'),
            subtitle: const Text('Personalise "Hi Pal", "HiPal" & "AiPal" to your voice'),
            leading: const Icon(Icons.tune_outlined),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const WakeEnrollmentScreen()),
            ),
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
          title: const Text('Sync phone calendar for today'),
          subtitle: const Text(
            'Read-only from your phone calendar apps. Also syncs when you open Today.',
          ),
          onTap: () async {
            final events = await CalendarService().fetchTodayEvents();
            if (!context.mounted) return;
            if (events.isEmpty) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('No events found for today')),
              );
              return;
            }
            final n = await context.read<AppState>().api.importCalendar(events);
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('Synced $n calendar event(s)')),
              );
            }
          },
        ),
        ListTile(
          title: const Text('Companion voice'),
          subtitle: Text(_voiceCatalogue
              .firstWhere(
                (v) => v['id'] == state.companionVoiceId,
                orElse: () => _voiceCatalogue.first,
              )['name'] as String),
          leading: const Icon(Icons.record_voice_over_outlined),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => _openVoicePicker(context, state),
        ),
        const Divider(),
        const ListTile(
          title: Text('Weekly summary email'),
          subtitle: Text('Preview and send your activity summary.'),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
          child: OutlinedButton.icon(
            icon: const Icon(Icons.email_outlined),
            label: const Text('Preview & Send'),
            onPressed: () => _previewAndSendWeeklySummary(context, state),
          ),
        ),
        const Divider(),
        ListTile(
          title: const Text('Open Spotify'),
          subtitle: const Text('AiPal controls music using Android deep links'),
          onTap: () async {
            final uri = Uri.parse('spotify:');
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
