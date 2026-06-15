import 'dart:async';

import 'package:flutter/material.dart';

class FocusTimerBar extends StatefulWidget {
  const FocusTimerBar({
    super.key,
    required this.taskTitle,
    required this.totalSeconds,
    required this.onComplete,
    required this.onCancel,
  });

  final String taskTitle;
  final int totalSeconds;
  final VoidCallback onComplete;
  final VoidCallback onCancel;

  @override
  State<FocusTimerBar> createState() => FocusTimerBarState();
}

class FocusTimerBarState extends State<FocusTimerBar> {
  late int _remaining;
  Timer? _timer;
  bool _paused = false;

  @override
  void initState() {
    super.initState();
    _remaining = widget.totalSeconds;
    _start();
  }

  void _start() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_paused) return;
      if (_remaining <= 1) {
        _timer?.cancel();
        widget.onComplete();
      } else {
        setState(() => _remaining--);
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  String get _label {
    final m = _remaining ~/ 60;
    final s = _remaining % 60;
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  double get _progress =>
      widget.totalSeconds > 0 ? _remaining / widget.totalSeconds : 0.0;

  @override
  Widget build(BuildContext context) {
    final gold = Theme.of(context).colorScheme.primary;
    return Material(
      elevation: 8,
      color: const Color(0xFF161B22),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              SizedBox(
                width: 84,
                height: 84,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    SizedBox(
                      width: 84,
                      height: 84,
                      child: CircularProgressIndicator(
                        value: _progress,
                        strokeWidth: 5,
                        backgroundColor: Colors.white12,
                        color: gold,
                      ),
                    ),
                    Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.timer_outlined, size: 14, color: gold.withValues(alpha: 0.8)),
                        Text(
                          _label,
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                fontFeatures: const [FontFeature.tabularFigures()],
                              ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'Focus',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.5),
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      widget.taskTitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: _paused ? 'Resume' : 'Pause',
                onPressed: () => setState(() => _paused = !_paused),
                icon: Icon(_paused ? Icons.play_arrow : Icons.pause),
              ),
              IconButton(
                tooltip: '+5 min',
                onPressed: () => setState(() => _remaining += 300),
                icon: const Icon(Icons.add),
              ),
              IconButton(
                tooltip: 'Complete',
                onPressed: widget.onComplete,
                icon: const Icon(Icons.check),
              ),
              IconButton(
                tooltip: 'Cancel',
                onPressed: widget.onCancel,
                icon: const Icon(Icons.close),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
