import 'package:flutter_test/flutter_test.dart';
import 'package:aipal/services/voice/voice_orchestrator.dart';
import 'package:aipal/services/voice/voice_state.dart';

void main() {
  test('voice orchestrator starts in idle state', () {
    final orchestrator = VoiceOrchestrator();

    expect(orchestrator.state, VoiceState.idle);
    expect(orchestrator.recentTransitions, isEmpty);
  });

  test('voice orchestrator allows expected transition chain', () {
    final orchestrator = VoiceOrchestrator();

    expect(
      orchestrator.transitionTo(
        VoiceState.wakeListening,
        event: VoiceEvent.wakeRouteActivated,
        reason: 'wake enabled',
      ),
      isTrue,
    );
    expect(
      orchestrator.transitionTo(
        VoiceState.listening,
        event: VoiceEvent.conversationStarted,
        reason: 'conversation started',
      ),
      isTrue,
    );
    expect(
      orchestrator.transitionTo(
        VoiceState.thinking,
        event: VoiceEvent.turnProcessingStarted,
        reason: 'turn processing',
      ),
      isTrue,
    );
    expect(
      orchestrator.transitionTo(
        VoiceState.speaking,
        event: VoiceEvent.ttsStarted,
        reason: 'tts started',
      ),
      isTrue,
    );

    expect(orchestrator.state, VoiceState.speaking);
    expect(orchestrator.recentTransitions.length, 4);
  });

  test('voice orchestrator rejects invalid transitions and records them', () {
    final orchestrator = VoiceOrchestrator();

    final changed = orchestrator.transitionTo(
      VoiceState.speaking,
      event: VoiceEvent.ttsStarted,
      reason: 'invalid from idle',
    );

    expect(changed, isFalse);
    expect(orchestrator.state, VoiceState.idle);
    expect(orchestrator.recentTransitions, isNotEmpty);
    expect(
      orchestrator.recentTransitions.last.reason,
      startsWith('invalid_transition:'),
    );
  });
}
