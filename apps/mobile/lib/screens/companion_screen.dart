import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import '../services/live_session.dart';
import '../widgets/aipal_logo.dart';
import '../widgets/orb_widget.dart';
import '../widgets/plan_draft_card.dart';
import 'text_chat_screen.dart';

class CompanionScreen extends StatefulWidget {
  const CompanionScreen({super.key});

  @override
  State<CompanionScreen> createState() => _CompanionScreenState();
}

class _CompanionScreenState extends State<CompanionScreen> {
  Timer? _thinkingTimer;
  bool _showStillThinking = false;
  LiveState? _lastLiveState;
  bool _showDiagnostics = false;

  @override
  void dispose() {
    _thinkingTimer?.cancel();
    super.dispose();
  }

  Future<void> _copyDiagnostics(AppState state) async {
    String buildLabel = 'unknown';
    try {
      final info = await PackageInfo.fromPlatform();
      buildLabel = '${info.version}+${info.buildNumber}';
    } catch (_) {}
    final transitions = state.voiceTransitions.reversed
        .take(6)
        .map(
          (t) =>
              '${t.event.name}: ${t.from.name} -> ${t.to.name} (${t.reason})',
        )
        .join('\n');
    final text = [
      'AiPal diagnostics ($buildLabel)',
      'voiceState=${state.voiceState.name}',
      'microphoneOwner=${state.microphoneOwner}',
      'wakeWordListening=${state.wakeWordListening}',
      'wakeWordError=${state.wakeWordError ?? "none"}',
      'liveError=${state.liveError ?? "none"}',
      'reminderError=${state.reminderError ?? "none"}',
      'greetingError=${state.greetingError ?? "none"}',
      'last transitions:',
      transitions.isEmpty ? '(none)' : transitions,
    ].join('\n');
    await Clipboard.setData(ClipboardData(text: text));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Diagnostics copied to clipboard')),
      );
    }
  }

  void _updateThinkingTimer(LiveState live, AppState state) {
    if (live == LiveState.thinking && _lastLiveState != LiveState.thinking) {
      _thinkingTimer?.cancel();
      _showStillThinking = false;
      _thinkingTimer = Timer(const Duration(seconds: 8), () {
        if (mounted && state.liveSession.state == LiveState.thinking) {
          setState(() => _showStillThinking = true);
        }
      });
    } else if (live != LiveState.thinking) {
      _thinkingTimer?.cancel();
      if (_showStillThinking) setState(() => _showStillThinking = false);
    }
    _lastLiveState = live;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, state, _) {
        final live = state.liveSession.state;
        _updateThinkingTimer(live, state);
        final inConvo = state.inConversation;
        final label = switch (live) {
          LiveState.resting => 'Resting',
          LiveState.thinking => 'Live — thinking',
          LiveState.speaking => 'Live — speaking',
          LiveState.listening => 'Live — listening',
        };
        return Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const AiPalBrandRow(),
                  GestureDetector(
                    onLongPress: () =>
                        setState(() => _showDiagnostics = !_showDiagnostics),
                    child: Chip(
                      label: Text(label),
                      backgroundColor: live == LiveState.resting
                          ? Colors.white12
                          : Theme.of(
                              context,
                            ).colorScheme.primary.withValues(alpha: 0.25),
                    ),
                  ),
                ],
              ),
              if (_showDiagnostics)
                Container(
                  width: double.infinity,
                  margin: const EdgeInsets.only(top: 10),
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.06),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: Colors.white.withValues(alpha: 0.16),
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Diagnostics (long-press status chip to hide)',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: Colors.white.withValues(alpha: 0.8),
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'voiceState=${state.voiceState.name} | micOwner=${state.microphoneOwner} | wakeListening=${state.wakeWordListening}',
                        style: TextStyle(
                          fontSize: 11,
                          color: Colors.white.withValues(alpha: 0.72),
                        ),
                      ),
                      const SizedBox(height: 6),
                      ...state.voiceTransitions.reversed
                          .take(4)
                          .map(
                            (t) => Text(
                              '${t.event.name}: ${t.from.name} -> ${t.to.name} (${t.reason})',
                              style: TextStyle(
                                fontSize: 10,
                                color: Colors.white.withValues(alpha: 0.62),
                              ),
                            ),
                          ),
                      const SizedBox(height: 6),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          onPressed: () => _copyDiagnostics(state),
                          icon: const Icon(Icons.copy, size: 14),
                          label: const Text(
                            'Copy diagnostics',
                            style: TextStyle(fontSize: 11),
                          ),
                          style: TextButton.styleFrom(
                            foregroundColor: Colors.white.withValues(
                              alpha: 0.8,
                            ),
                            visualDensity: VisualDensity.compact,
                            padding: EdgeInsets.zero,
                            minimumSize: const Size(0, 0),
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              if (state.wakeWordError != null && state.wakeWordEnabled)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    state.wakeWordError!,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 12,
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              // Bug #1 fix: rendered unconditionally (not gated on inConvo)
              // so Live-mode start/runtime failures are always visible —
              // previously this was hidden because _endConversation() ran
              // before the next frame and flipped inConvo to false first.
              if (state.liveError != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: GestureDetector(
                    onTap: () => state.clearLiveError(),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: Theme.of(
                          context,
                        ).colorScheme.error.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: Theme.of(
                            context,
                          ).colorScheme.error.withValues(alpha: 0.4),
                        ),
                      ),
                      child: Text(
                        state.liveError!,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 12,
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ),
                  ),
                ),
              if (_showStillThinking)
                Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 10,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.orange.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: Colors.orange.withValues(alpha: 0.4),
                      ),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(
                          Icons.hourglass_top,
                          size: 16,
                          color: Colors.orange,
                        ),
                        const SizedBox(width: 8),
                        const Expanded(
                          child: Text(
                            'Still thinking… tap the orb to cancel',
                            style: TextStyle(
                              color: Colors.orange,
                              fontSize: 13,
                            ),
                          ),
                        ),
                        GestureDetector(
                          onTap: () => state.toggleLive(),
                          child: const Icon(
                            Icons.close,
                            size: 18,
                            color: Colors.orange,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              if (state.wakeWordListening)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    defaultTargetPlatform == TargetPlatform.android
                        ? 'Listening for Hi Pal — works in background too'
                        : 'Say Hi Pal to start',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 13,
                      color: Theme.of(
                        context,
                      ).colorScheme.primary.withValues(alpha: 0.85),
                    ),
                  ),
                )
              else if (state.wakeWordEnabled &&
                  !inConvo &&
                  live == LiveState.resting)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Column(
                    // Round 9 fix: distinguish a transient restart (normal,
                    // takes up to ~9s after every Live session per
                    // _restartWakeAfterLive's 800ms settle + up to 8s
                    // ensureRunning wait) from a genuine failure
                    // (wakeWordError set). Previously an actionable "Retry
                    // listener" button appeared immediately in BOTH cases,
                    // making the normal restart window look broken.
                    children: state.wakeWordError == null
                        ? [
                            const SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              'Hi Pal enabled — starting listener…',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontSize: 13,
                                color: Colors.white.withValues(alpha: 0.45),
                              ),
                            ),
                          ]
                        : [
                            Text(
                              'Hi Pal enabled — starting listener…',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontSize: 13,
                                color: Colors.white.withValues(alpha: 0.45),
                              ),
                            ),
                            const SizedBox(height: 6),
                            TextButton.icon(
                              onPressed: () => state.syncWakeListener(),
                              icon: const Icon(Icons.refresh, size: 16),
                              label: const Text('Retry listener'),
                              style: TextButton.styleFrom(
                                foregroundColor: Theme.of(
                                  context,
                                ).colorScheme.primary,
                                visualDensity: VisualDensity.compact,
                              ),
                            ),
                          ],
                  ),
                ),
              if (kIsWeb && state.wakeWordEnabled)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    'Wake word works on the Android app. On web, tap the orb to go Live.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.white.withValues(alpha: 0.55),
                    ),
                  ),
                ),
              if (state.checkinBanner != null && live == LiveState.resting)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    state.checkinBanner!,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 13,
                      color: Colors.white.withValues(alpha: 0.6),
                    ),
                  ),
                ),
              if (live == LiveState.resting && state.nextOpenTask != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: ActionChip(
                    avatar: Icon(
                      Icons.arrow_forward,
                      size: 16,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                    label: Text(
                      'Up next: ${state.nextOpenTask!['title']}',
                      overflow: TextOverflow.ellipsis,
                    ),
                    onPressed: () => state.goToTab(1),
                  ),
                ),
              const Spacer(),
              OrbWidget(state: live, onTap: () => state.toggleLive()),
              const SizedBox(height: 24),
              if (state.lastReply != null && inConvo)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Text(
                    state.lastReply!,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.85),
                      height: 1.4,
                    ),
                  ),
                ),
              if (state.pendingPlanDraft != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
                  child: PlanDraftCard(
                    draft: state.pendingPlanDraft!,
                    onConfirm: () => state.confirmPlanDraft(),
                    onDiscard: () => state.discardPlanDraft(),
                  ),
                ),
              const Spacer(),
              OutlinedButton.icon(
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const TextChatScreen()),
                  );
                },
                icon: const Icon(Icons.chat_bubble_outline),
                label: const Text('Text mode'),
              ),
              const SizedBox(height: 12),
              Text(
                !inConvo
                    ? (state.wakeWordListening
                          ? (defaultTargetPlatform == TargetPlatform.android
                                ? 'Say Hi Pal anywhere or tap the orb to go Live'
                                : 'Say Hi Pal or tap the orb to go Live')
                          : 'Tap the orb to go Live')
                    : live == LiveState.listening
                    ? 'Listening… tap orb to end · stays open for follow-ups'
                    : live == LiveState.speaking
                    ? 'Speaking… you can interrupt or wait'
                    : 'Working on that…',
                style: TextStyle(
                  fontSize: 12,
                  color: Colors.white.withValues(alpha: 0.5),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
