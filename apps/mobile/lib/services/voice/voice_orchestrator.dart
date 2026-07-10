import 'voice_state.dart';

class VoiceTransition {
  const VoiceTransition({
    required this.from,
    required this.to,
    required this.event,
    required this.reason,
    required this.at,
    this.sessionId,
    this.data,
  });

  final VoiceState from;
  final VoiceState to;
  final VoiceEvent event;
  final String reason;
  final DateTime at;
  final String? sessionId;
  final Map<String, dynamic>? data;

  Map<String, dynamic> toJson() => {
    'from': from.name,
    'to': to.name,
    'event': event.name,
    'reason': reason,
    'at': at.toIso8601String(),
    if (sessionId != null) 'session_id': sessionId,
    if (data != null) 'data': data,
  };
}

class VoiceOrchestrator {
  VoiceState _state = VoiceState.idle;
  final List<VoiceTransition> _recentTransitions = [];

  VoiceState get state => _state;
  List<VoiceTransition> get recentTransitions =>
      List.unmodifiable(_recentTransitions);

  bool transitionTo(
    VoiceState next, {
    required VoiceEvent event,
    required String reason,
    String? sessionId,
    Map<String, dynamic>? data,
  }) {
    final current = _state;
    if (current == next) {
      _record(
        VoiceTransition(
          from: current,
          to: next,
          event: event,
          reason: reason,
          at: DateTime.now().toUtc(),
          sessionId: sessionId,
          data: data,
        ),
      );
      return false;
    }

    if (!canTransition(current, next)) {
      _record(
        VoiceTransition(
          from: current,
          to: current,
          event: event,
          reason: 'invalid_transition:$reason',
          at: DateTime.now().toUtc(),
          sessionId: sessionId,
          data: {'requested_to': next.name, ...?data},
        ),
      );
      return false;
    }

    _state = next;
    _record(
      VoiceTransition(
        from: current,
        to: next,
        event: event,
        reason: reason,
        at: DateTime.now().toUtc(),
        sessionId: sessionId,
        data: data,
      ),
    );
    return true;
  }

  bool canTransition(VoiceState from, VoiceState to) {
    const table = {
      VoiceState.idle: {
        VoiceState.wakeListening,
        VoiceState.listening,
        VoiceState.error,
      },
      VoiceState.wakeListening: {
        VoiceState.listening,
        VoiceState.idle,
        VoiceState.error,
      },
      VoiceState.listening: {
        VoiceState.recording,
        VoiceState.thinking,
        VoiceState.speaking,
        VoiceState.cooldown,
        VoiceState.wakeListening,
        VoiceState.idle,
        VoiceState.error,
      },
      VoiceState.recording: {
        VoiceState.thinking,
        VoiceState.listening,
        VoiceState.cooldown,
        VoiceState.error,
      },
      VoiceState.thinking: {
        VoiceState.speaking,
        VoiceState.listening,
        VoiceState.cooldown,
        VoiceState.error,
      },
      VoiceState.speaking: {
        VoiceState.listening,
        VoiceState.cooldown,
        VoiceState.error,
      },
      VoiceState.cooldown: {
        VoiceState.wakeListening,
        VoiceState.listening,
        VoiceState.idle,
        VoiceState.error,
      },
      VoiceState.error: {
        VoiceState.idle,
        VoiceState.wakeListening,
        VoiceState.listening,
      },
    };

    return table[from]?.contains(to) ?? false;
  }

  void _record(VoiceTransition entry) {
    _recentTransitions.add(entry);
    if (_recentTransitions.length > 40) {
      _recentTransitions.removeAt(0);
    }
  }
}
