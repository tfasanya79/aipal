enum VoiceState {
  idle,
  wakeListening,
  listening,
  recording,
  thinking,
  speaking,
  cooldown,
  error,
}

enum VoiceEvent {
  appBootstrapped,
  wakeRouteActivated,
  wakeRouteDeactivated,
  conversationStarted,
  speechDetected,
  turnProcessingStarted,
  turnProcessingFinished,
  ttsStarted,
  ttsFinished,
  conversationEnded,
  errorDetected,
  externalSync,
}
