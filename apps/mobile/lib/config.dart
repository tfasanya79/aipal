class AppConfig {
  static const apiBase = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://43.160.220.9.sslip.io/api/v2',
  );

  static String wsUrl(String token) {
    final base = apiBase.replaceFirst('https://', 'wss://').replaceFirst('http://', 'ws://');
    return '$base/ws/session?token=$token';
  }
}
