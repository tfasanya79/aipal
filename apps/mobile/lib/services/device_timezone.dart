import 'package:flutter_timezone/flutter_timezone.dart';

/// Device IANA timezone for profile sync and server-side scheduling.
Future<String> deviceIanaTimezone() async {
  try {
    final tz = await FlutterTimezone.getLocalTimezone();
    if (tz.isNotEmpty) return tz;
  } catch (_) {}
  return 'UTC';
}
