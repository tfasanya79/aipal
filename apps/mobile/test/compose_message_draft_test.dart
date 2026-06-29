import 'package:aipal/services/compose_message_draft.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('buildComposeDraftPrompt includes channel and intent', () {
    final prompt = buildComposeDraftPrompt(
      channel: ComposeChannel.email,
      intent: 'thank my manager for feedback',
    );

    expect(prompt, contains('Email'));
    expect(prompt, contains('thank my manager for feedback'));
    expect(prompt, contains('Do not send anything.'));
  });

  test('normalizeDraftText trims wrapped quotes', () {
    expect(normalizeDraftText('"Hello there"'), 'Hello there');
    expect(normalizeDraftText("'Hello there'"), 'Hello there');
    expect(normalizeDraftText('Hello there'), 'Hello there');
  });

  test('buildComposeUri returns SMS uri with body', () {
    final uri = buildComposeUri(channel: ComposeChannel.sms, body: 'Hi there');
    expect(uri.scheme, 'sms');
    expect(uri.queryParameters['body'], 'Hi there');
  });

  test('buildComposeUri returns mailto uri with body', () {
    final uri = buildComposeUri(channel: ComposeChannel.email, body: 'Hello');
    expect(uri.scheme, 'mailto');
    expect(uri.queryParameters['body'], 'Hello');
  });
}
