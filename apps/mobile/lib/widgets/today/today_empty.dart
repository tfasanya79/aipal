import 'package:flutter/material.dart';

class TodayEmpty extends StatelessWidget {
  const TodayEmpty({super.key, this.onGoCompanion});

  final VoidCallback? onGoCompanion;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    const Color(0xFFE8A838).withValues(alpha: 0.9),
                    const Color(0xFF9B7EDE).withValues(alpha: 0.35),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 20),
            Text('Nothing planned yet', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              'Tell AiPal on Companion what you want to do today.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white.withValues(alpha: 0.6)),
            ),
            if (onGoCompanion != null) ...[
              const SizedBox(height: 20),
              OutlinedButton(onPressed: onGoCompanion, child: const Text('Open Companion')),
            ],
          ],
        ),
      ),
    );
  }
}
