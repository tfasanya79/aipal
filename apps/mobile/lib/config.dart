class AppConfig {
  static const apiBase = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://43.160.220.9.sslip.io/api/v2',
  );

  /// Live Voice v2: full-duplex WebSocket + PCM streaming (native).
  static const liveVoiceV2 = bool.fromEnvironment('LIVE_VOICE_V2', defaultValue: false);

  static String wsUrl(String token) {
    final base = apiBase.replaceFirst('https://', 'wss://').replaceFirst('http://', 'ws://');
    return '$base/ws/session?token=$token';
  }
}
