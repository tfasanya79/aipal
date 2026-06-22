import 'package:flutter/material.dart';

import 'task_category.dart';

class UpNextCard extends StatelessWidget {
  const UpNextCard({
    super.key,
    required this.task,
    this.onStartFocus,
    this.onDone,
    this.onBreakdown,
    this.onEdit,
  });

  final Map<String, dynamic> task;
  final VoidCallback? onStartFocus;
  final VoidCallback? onDone;
  final VoidCallback? onBreakdown;
  final VoidCallback? onEdit;

  @override
  Widget build(BuildContext context) {
    final subs = (task['subtasks'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final color = categoryColor(task['category'] as String?);
    final est = formatEstimate(task['estimated_minutes'] as int?);
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border(left: BorderSide(color: color, width: 4)),
        ),
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Up next', style: TextStyle(color: Colors.white.withValues(alpha: 0.55), fontSize: 12)),
            const SizedBox(height: 6),
            Text(task['title'] as String, style: Theme.of(context).textTheme.titleMedium),
            if (est.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Chip(
                  visualDensity: VisualDensity.compact,
                  label: Text(est),
                  backgroundColor: color.withValues(alpha: 0.2),
                ),
              ),
            if (subs.isNotEmpty) ...[
              const SizedBox(height: 8),
              ...subs.map((s) => Padding(
                    padding: const EdgeInsets.only(left: 8, top: 4),
                    child: Text('• ${s['title']}', style: TextStyle(color: Colors.white.withValues(alpha: 0.7), fontSize: 13)),
                  )),
            ],
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              children: [
                FilledButton.icon(
                  onPressed: onStartFocus,
                  icon: const Icon(Icons.timer_outlined, size: 18),
                  label: const Text('Start focus'),
                ),
                OutlinedButton(onPressed: onDone, child: const Text('Done')),
                if (onEdit != null)
                  TextButton.icon(
                    onPressed: onEdit,
                    icon: const Icon(Icons.edit_outlined, size: 18),
                    label: const Text('Edit'),
                  ),
                if (subs.isEmpty && onBreakdown != null)
                  TextButton(onPressed: onBreakdown, child: const Text('Break down')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
