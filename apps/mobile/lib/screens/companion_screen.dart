import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
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

  @override
  void dispose() {
    _thinkingTimer?.cancel();
    super.dispose();
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
                  Chip(
                    label: Text(label),
                    backgroundColor: live == LiveState.resting
                        ? Colors.white12
                        : Theme.of(context).colorScheme.primary.withValues(alpha: 0.25),
                  ),
                ],
              ),
              if (state.wakeWordError != null && state.wakeWordEnabled)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    state.wakeWordError!,
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.error),
                  ),
                ),
              if (_showStillThinking)
                Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                    decoration: BoxDecoration(
                      color: Colors.orange.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.orange.withValues(alpha: 0.4)),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.hourglass_top, size: 16, color: Colors.orange),
                        const SizedBox(width: 8),
                        const Expanded(
                          child: Text(
                            'Still thinking… tap the orb to cancel',
                            style: TextStyle(color: Colors.orange, fontSize: 13),
                          ),
                        ),
                        GestureDetector(
                          onTap: () => state.toggleLive(),
                          child: const Icon(Icons.close, size: 18, color: Colors.orange),
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
                      color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.85),
                    ),
                  ),
                )
              else if (state.wakeWordEnabled && !inConvo && live == LiveState.resting)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    'Hi Pal enabled — starting listener…',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 13,
                      color: Colors.white.withValues(alpha: 0.45),
                    ),
                  ),
                ),
              if (kIsWeb && state.wakeWordEnabled)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    'Wake word works on the Android app. On web, tap the orb to go Live.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12, color: Colors.white.withValues(alpha: 0.55)),
                  ),
                ),
              if (state.checkinBanner != null && live == LiveState.resting)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    state.checkinBanner!,
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 13, color: Colors.white.withValues(alpha: 0.6)),
                  ),
                ),
              if (live == LiveState.resting && state.nextOpenTask != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: ActionChip(
                    avatar: Icon(Icons.arrow_forward, size: 16, color: Theme.of(context).colorScheme.primary),
                    label: Text(
                      'Up next: ${state.nextOpenTask!['title']}',
                      overflow: TextOverflow.ellipsis,
                    ),
                    onPressed: () => state.goToTab(1),
                  ),
                ),
              const Spacer(),
              OrbWidget(
                state: live,
                onTap: () => state.toggleLive(),
              ),
              const SizedBox(height: 24),
              if (state.lastReply != null && inConvo)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Text(
                    state.lastReply!,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white.withValues(alpha: 0.85), height: 1.4),
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
                style: TextStyle(fontSize: 12, color: Colors.white.withValues(alpha: 0.5)),
              ),
            ],
          ),
        );
      },
    );
  }
}
