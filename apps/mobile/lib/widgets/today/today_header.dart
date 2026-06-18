import 'package:flutter/material.dart';

import '../aipal_logo.dart';

class TodayHeader extends StatelessWidget {
  const TodayHeader({
    super.key,
    this.streakDays = 0,
    this.onReview,
  });

  final int streakDays;
  final VoidCallback? onReview;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 8, 0),
      child: Row(
        children: [
          const Expanded(
            child: AiPalBrandRow(logoSize: 18, orbSize: 18),
          ),
          if (streakDays > 0)
            Padding(
              padding: const EdgeInsets.only(right: 4),
              child: Text(
                '$streakDays day streak',
                style: TextStyle(color: Theme.of(context).colorScheme.primary, fontSize: 12),
              ),
            ),
          if (onReview != null)
            IconButton(
              tooltip: 'Review your day',
              onPressed: onReview,
              icon: const Icon(Icons.nightlight_round),
            ),
        ],
      ),
    );
  }
}
