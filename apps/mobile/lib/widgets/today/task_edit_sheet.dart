import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

class TaskEditSheet extends StatefulWidget {
  const TaskEditSheet({
    super.key,
    required this.task,
    required this.onSave,
  });

  final Map<String, dynamic> task;
  final Future<void> Function(String title, DateTime dueLocal, int minutes)
      onSave;

  static const _durationOptions = [15, 30, 45, 60, 90, 120];

  @override
  State<TaskEditSheet> createState() => _TaskEditSheetState();
}

class _TaskEditSheetState extends State<TaskEditSheet> {
  late TimeOfDay _time;
  late int _minutes;
  late final TextEditingController _titleController;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final due = widget.task['due_at'] as String?;
    if (due != null) {
      try {
        final dt = DateTime.parse(due).toLocal();
        _time = TimeOfDay(hour: dt.hour, minute: dt.minute);
      } catch (_) {
        _time = TimeOfDay.now();
      }
    } else {
      _time = TimeOfDay.now();
    }
    _minutes = widget.task['estimated_minutes'] as int? ?? 30;
    _titleController = TextEditingController(
      text: widget.task['title'] as String? ?? '',
    );
  }

  @override
  void dispose() {
    _titleController.dispose();
    super.dispose();
  }

  DateTime _dueLocalToday() {
    final now = DateTime.now();
    return DateTime(now.year, now.month, now.day, _time.hour, _time.minute);
  }

  Future<void> _pickTime() async {
    final picked = await showTimePicker(context: context, initialTime: _time);
    if (picked != null) setState(() => _time = picked);
  }

  Future<void> _save() async {
    final title = _titleController.text.trim();
    if (title.isEmpty) return;
    setState(() => _saving = true);
    try {
      await widget.onSave(title, _dueLocalToday(), _minutes);
      if (mounted) Navigator.pop(context);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final dueLabel = DateFormat.jm().format(_dueLocalToday());

    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Edit task', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          TextField(
            controller: _titleController,
            textCapitalization: TextCapitalization.sentences,
            decoration: const InputDecoration(
              labelText: 'Title',
              border: OutlineInputBorder(),
              isDense: true,
            ),
          ),
          const SizedBox(height: 16),
          OutlinedButton.icon(
            onPressed: _pickTime,
            icon: const Icon(Icons.schedule_outlined),
            label: Text('Time: $dueLabel'),
          ),
          const SizedBox(height: 12),
          Text('Duration', style: TextStyle(color: Colors.white.withValues(alpha: 0.55), fontSize: 13)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: TaskEditSheet._durationOptions.map((m) {
              final selected = _minutes == m;
              return ChoiceChip(
                visualDensity: VisualDensity.compact,
                label: Text('${m}m'),
                selected: selected,
                onSelected: (_) => setState(() => _minutes = m),
              );
            }).toList(),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Save'),
          ),
        ],
      ),
    );
  }
}
