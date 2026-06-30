import 'package:url_launcher/url_launcher.dart';

class MusicCommandService {
  const MusicCommandService._();

  static Future<bool> launchSpotify(Map<String, dynamic> command) async {
    final action = (command['action'] as String? ?? 'play').toLowerCase();
    final query = (command['query'] as String? ?? '').trim();

    if (action == 'play') {
      final target = query.isNotEmpty
          ? Uri.parse('spotify:search:${Uri.encodeComponent(query)}')
          : Uri.parse('spotify:');
      return launchUrl(target, mode: LaunchMode.externalApplication);
    }

    final target = Uri.parse('spotify:');
    return launchUrl(target, mode: LaunchMode.externalApplication);
  }
}
