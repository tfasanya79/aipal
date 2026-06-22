import 'package:flutter/material.dart';

class RoutineChips extends StatelessWidget {
  const RoutineChips({
    super.key,
    required this.onSelect,
    this.busy = false,
  });

  final void Function(String template) onSelect;
  final bool busy;

  static const _routines = [
    (template: 'plan_day', label: 'Plan day', icon: Icons.wb_sunny_outlined),
    (template: 'deep_work', label: 'Deep work', icon: Icons.psychology_outlined),
    (template: 'break', label: 'Break', icon: Icons.self_improvement_outlined),
    (template: 'errands', label: 'Errands', icon: Icons.checklist_outlined),
  ];

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
          child: Text(
            'Suggest routines',
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.5),
              fontWeight: FontWeight.w600,
              fontSize: 13,
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _routines.map((r) {
              return ActionChip(
                visualDensity: VisualDensity.compact,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                avatar: Icon(r.icon, size: 16, color: Theme.of(context).colorScheme.primary),
                label: Text(r.label),
                onPressed: busy ? null : () => onSelect(r.template),
              );
            }).toList(),
          ),
        ),
      ],
    );
  }
}
