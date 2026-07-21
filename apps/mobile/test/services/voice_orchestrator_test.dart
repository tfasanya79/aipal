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

  // Regression tests for a real production bug (build 126, 2026-07-21):
  // _endConversation() in app_state.dart transitions to VoiceState.idle
  // whenever wake word is disabled, regardless of which active-conversation
  // state the app was in when the conversation ended (listening, recording,
  // thinking, or speaking). Only VoiceState.listening allowed a transition to
  // idle -- ending a conversation while recording/thinking/speaking (e.g. a
  // turn that finishes mid-processing, or a mid-TTS interruption) silently
  // failed the transition and left `state` permanently wedged, which then
  // also rejected every subsequent wake-route transition attempt checked
  // against that stale state.
  test('voice orchestrator allows recording -> idle via conversationEnded', () {
    final orchestrator = VoiceOrchestrator();
    orchestrator.transitionTo(
      VoiceState.wakeListening,
      event: VoiceEvent.wakeRouteActivated,
      reason: 'wake enabled',
    );
    orchestrator.transitionTo(
      VoiceState.listening,
      event: VoiceEvent.conversationStarted,
      reason: 'conversation started',
    );
    orchestrator.transitionTo(
      VoiceState.recording,
      event: VoiceEvent.speechDetected,
      reason: 'vad_speech_start',
    );

    final changed = orchestrator.transitionTo(
      VoiceState.idle,
      event: VoiceEvent.conversationEnded,
      reason: 'conversation_ended',
    );

    expect(changed, isTrue);
    expect(orchestrator.state, VoiceState.idle);
  });

  test('voice orchestrator allows thinking -> idle via conversationEnded', () {
    final orchestrator = VoiceOrchestrator();
    orchestrator.transitionTo(
      VoiceState.wakeListening,
      event: VoiceEvent.wakeRouteActivated,
      reason: 'wake enabled',
    );
    orchestrator.transitionTo(
      VoiceState.listening,
      event: VoiceEvent.conversationStarted,
      reason: 'conversation started',
    );
    orchestrator.transitionTo(
      VoiceState.thinking,
      event: VoiceEvent.turnProcessingStarted,
      reason: 'turn processing',
    );

    final changed = orchestrator.transitionTo(
      VoiceState.idle,
      event: VoiceEvent.conversationEnded,
      reason: 'conversation_ended',
    );

    expect(changed, isTrue);
    expect(orchestrator.state, VoiceState.idle);
  });

  test('voice orchestrator allows speaking -> idle via conversationEnded', () {
    final orchestrator = VoiceOrchestrator();
    orchestrator.transitionTo(
      VoiceState.wakeListening,
      event: VoiceEvent.wakeRouteActivated,
      reason: 'wake enabled',
    );
    orchestrator.transitionTo(
      VoiceState.listening,
      event: VoiceEvent.conversationStarted,
      reason: 'conversation started',
    );
    orchestrator.transitionTo(
      VoiceState.thinking,
      event: VoiceEvent.turnProcessingStarted,
      reason: 'turn processing',
    );
    orchestrator.transitionTo(
      VoiceState.speaking,
      event: VoiceEvent.ttsStarted,
      reason: 'tts started',
    );

    final changed = orchestrator.transitionTo(
      VoiceState.idle,
      event: VoiceEvent.conversationEnded,
      reason: 'conversation_ended',
    );

    expect(changed, isTrue);
    expect(orchestrator.state, VoiceState.idle);
  });
}
