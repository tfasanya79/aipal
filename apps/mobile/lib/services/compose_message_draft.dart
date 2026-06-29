enum ComposeChannel { sms, email }

String composeChannelLabel(ComposeChannel channel) {
  switch (channel) {
    case ComposeChannel.sms:
      return 'SMS';
    case ComposeChannel.email:
      return 'Email';
  }
}

String buildComposeDraftPrompt({
  required ComposeChannel channel,
  required String intent,
}) {
  final target = composeChannelLabel(channel);
  return '''
Draft a $target message based on this user intent.
- Keep it concise and natural.
- Return only the message text with no intro, no markdown, and no quotes.
- Do not send anything.
Intent: $intent
''';
}

String normalizeDraftText(String raw) {
  final trimmed = raw.trim();
  if (trimmed.length >= 2) {
    final startsDouble = trimmed.startsWith('"');
    final endsDouble = trimmed.endsWith('"');
    final startsSingle = trimmed.startsWith("'");
    final endsSingle = trimmed.endsWith("'");
    if ((startsDouble && endsDouble) || (startsSingle && endsSingle)) {
      return trimmed.substring(1, trimmed.length - 1).trim();
    }
  }
  return trimmed;
}

Uri buildComposeUri({
  required ComposeChannel channel,
  required String body,
}) {
  switch (channel) {
    case ComposeChannel.sms:
      return Uri(
        scheme: 'sms',
        queryParameters: {'body': body},
      );
    case ComposeChannel.email:
      return Uri(
        scheme: 'mailto',
        queryParameters: {'body': body},
      );
  }
}
