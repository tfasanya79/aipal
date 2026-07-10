/// Typed voice pipeline error categories (ChatGPT review item #7).
///
/// Instead of ad-hoc try/catch/retry scattered per service with raw
/// exception strings leaking to the UI, every voice-pipeline failure is
/// classified into one of these categories so the orchestrator/AppState can
/// decide on a consistent recovery strategy and surface a clear, user-safe
/// message instead of `e.toString()`.
enum VoiceErrorCategory {
  microphone,
  wakeModel,
  network,
  stt,
  llm,
  tts,
  unknown,
}

class VoiceError {
  const VoiceError({
    required this.category,
    required this.userMessage,
    this.cause,
    this.detail,
  });

  final VoiceErrorCategory category;

  /// Safe, user-facing message (never a raw exception string).
  final String userMessage;

  /// The original exception/error object, if any (for logging only).
  final Object? cause;

  /// Optional technical detail string for diagnostics/logging (not shown
  /// directly to the user).
  final String? detail;

  Map<String, dynamic> toJson() => {
    'category': category.name,
    'message': userMessage,
    if (detail != null) 'detail': detail,
    if (cause != null) 'cause': cause.toString(),
  };

  @override
  String toString() => userMessage;

  /// Classifies a caught exception/error into a [VoiceError] with a safe
  /// user-facing message. This replaces the previous pattern of setting
  /// `lastReply = e.toString()` directly from raw exceptions.
  factory VoiceError.classify(Object error, {String? contextDetail}) {
    final text = error.toString().toLowerCase();
    if (error is StateError && text.contains('microphone')) {
      return VoiceError(
        category: VoiceErrorCategory.microphone,
        userMessage:
            'The microphone is busy right now. Please try again in a moment.',
        cause: error,
        detail: contextDetail ?? error.toString(),
      );
    }
    if (text.contains('permission')) {
      return VoiceError(
        category: VoiceErrorCategory.microphone,
        userMessage: 'Microphone permission is required for Live voice mode.',
        cause: error,
        detail: contextDetail ?? error.toString(),
      );
    }
    if (text.contains('timeout') ||
        text.contains('socket') ||
        text.contains('connection') ||
        text.contains('network') ||
        text.contains('failed host lookup')) {
      return VoiceError(
        category: VoiceErrorCategory.network,
        userMessage:
            'Connection trouble reaching AiPal. Please check your network and try again.',
        cause: error,
        detail: contextDetail ?? error.toString(),
      );
    }
    if (text.contains('openwakeword') || text.contains('wake')) {
      return VoiceError(
        category: VoiceErrorCategory.wakeModel,
        userMessage: 'Hi Pal wake listener could not start. Tap retry.',
        cause: error,
        detail: contextDetail ?? error.toString(),
      );
    }
    return VoiceError(
      category: VoiceErrorCategory.unknown,
      userMessage: 'Something went wrong starting Live mode. Please try again.',
      cause: error,
      detail: contextDetail ?? error.toString(),
    );
  }
}
