import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

class TodayHeroCard extends StatelessWidget {
  const TodayHeroCard({
    super.key,
    required this.openCount,
    required this.done,
    required this.total,
    required this.wakeName,
  });

  final int openCount;
  final int done;
  final int total;
  final String wakeName;

  String get _palLine {
    if (openCount == 0) {
      return total > 0 && done == total
          ? 'All done for today, $wakeName.'
          : 'Nothing on Today yet, $wakeName.';
    }
    if (openCount == 1) return '1 thing left today, $wakeName.';
    return '$openCount things left today, $wakeName.';
  }

  @override
  Widget build(BuildContext context) {
    final dateLabel = DateFormat('EEEE, MMM d').format(DateTime.now());
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Material(
        borderRadius: BorderRadius.circular(16),
        color: theme.colorScheme.primary,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Today',
                      style: theme.textTheme.titleMedium?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      dateLabel,
                      style: TextStyle(color: Colors.white.withValues(alpha: 0.85), fontSize: 13),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      _palLine,
                      style: TextStyle(color: Colors.white.withValues(alpha: 0.92), fontSize: 14),
                    ),
                    if (total > 0) ...[
                      const SizedBox(height: 6),
                      Text(
                        '$done of $total done',
                        style: TextStyle(color: Colors.white.withValues(alpha: 0.75), fontSize: 12),
                      ),
                    ],
                  ],
                ),
              ),
              Text(
                '$openCount',
                style: theme.textTheme.displayMedium?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                  height: 1,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
