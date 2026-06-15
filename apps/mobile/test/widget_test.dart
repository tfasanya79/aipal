import 'package:aipal/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('App boots', (tester) async {
    await tester.pumpWidget(const AipalApp());
    expect(find.textContaining('AiPal'), findsWidgets);
  });
}
