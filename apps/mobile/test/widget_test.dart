import 'package:aipal/main.dart';
import 'package:aipal/providers/app_state.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('App boots', (tester) async {
    final appState = AppState();
    await tester.pumpWidget(AipalApp(appState: appState));
    expect(find.textContaining('AiPal'), findsWidgets);
  });
}
