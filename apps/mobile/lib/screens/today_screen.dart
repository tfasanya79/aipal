import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import '../widgets/plan_draft_card.dart';
import '../widgets/today/focus_timer_bar.dart';
import '../widgets/today/priority_lanes.dart';
import '../widgets/today/review_today_sheet.dart';
import '../widgets/today/routine_chips.dart';
import '../widgets/today/task_edit_sheet.dart';
import '../widgets/today/timeline_task_tile.dart';
import '../widgets/today/today_empty.dart';
import '../widgets/today/today_header.dart';
import '../widgets/today/today_hero_card.dart';
import '../widgets/today/up_next_card.dart';

class TodayScreen extends StatefulWidget {
  const TodayScreen({super.key});

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> {
  bool _completedExpanded = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AppState>().refreshTodayView();
    });
  }

  Future<void> _suggestDay(AppState state, {String? template}) async {
    await state.suggestDayPlan(template: template);
    if (!mounted) return;
    final notice = state.suggestDayNotice;
    if (notice != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(notice)));
      state.clearSuggestDayNotice();
    }
  }

  Future<void> _addTask() async {
    final controller = TextEditingController();
    final title = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add task'),
        content: TextField(controller: controller, autofocus: true, decoration: const InputDecoration(hintText: 'What needs doing?')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, controller.text.trim()), child: const Text('Add')),
        ],
      ),
    );
    if (title != null && title.isNotEmpty && mounted) {
      await context.read<AppState>().createTask(title);
    }
  }

  void _openReview(AppState state) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF161B22),
      builder: (_) => ReviewTodaySheet(
        payload: state.eveningPayload ?? {},
        openTasks: state.openTasksForReview,
        onDefer: () async {
          Navigator.pop(context);
          await state.deferOpenTasks();
        },
        onGoLive: () {
          Navigator.pop(context);
          state.goToTab(0);
          state.toggleLive();
        },
      ),
    );
  }

  void _editTask(AppState state, Map<String, dynamic> task) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF161B22),
      builder: (_) => TaskEditSheet(
        task: task,
        onSave: (due, mins) => state.updateTaskSchedule(task['id'] as int, due, mins),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, state, _) {
        final view = state.todayView;
        final summary = view?['summary'] as Map<String, dynamic>?;
        final sections = view?['sections'] as Map<String, dynamic>?;
        final upNext = view?['up_next'] as Map<String, dynamic>?;
        final now = (sections?['now'] as List?)?.cast<Map<String, dynamic>>() ?? [];
        final upcoming = (sections?['upcoming'] as List?)?.cast<Map<String, dynamic>>() ?? [];
        final completed = (sections?['completed'] as List?)?.cast<Map<String, dynamic>>() ?? [];
        final focus = state.focusTask;
        final planDraft = state.pendingPlanDraft;
        final wakeName = state.profile?['wake_name'] as String? ??
            state.profile?['display_name'] as String? ??
            'friend';
        final openCount = summary?['open'] as int? ?? 0;
        final done = summary?['done'] as int? ?? 0;
        final total = summary?['total'] as int? ?? 0;

        return Scaffold(
          floatingActionButton: FloatingActionButton(
            onPressed: _addTask,
            child: const Icon(Icons.add),
          ),
          body: Column(
            children: [
              if (focus != null)
                FocusTimerBar(
                  taskTitle: focus['title'] as String,
                  totalSeconds: state.focusSeconds,
                  onComplete: () => state.completeFocusTask(),
                  onCancel: () => state.cancelFocus(),
                ),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: state.refreshTodayView,
                  child: view == null
                      ? const Center(child: CircularProgressIndicator())
                      : (summary?['total'] as int? ?? 0) == 0 && upNext == null
                          ? ListView(
                              children: [
                                TodayHeader(onReview: () => _loadAndReview(state)),
                                TodayHeroCard(
                                  openCount: 0,
                                  done: 0,
                                  total: 0,
                                  wakeName: wakeName,
                                ),
                                RoutineChips(
                                  busy: state.loading,
                                  onSelect: (t) => _suggestDay(state, template: t),
                                ),
                                Padding(
                                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                                  child: OutlinedButton.icon(
                                    onPressed: state.loading ? null : () => _suggestDay(state),
                                    icon: state.loading
                                        ? const SizedBox(
                                            width: 16,
                                            height: 16,
                                            child: CircularProgressIndicator(strokeWidth: 2),
                                          )
                                        : const Icon(Icons.auto_awesome_outlined),
                                    label: const Text('Suggest for me'),
                                  ),
                                ),
                                if (planDraft != null)
                                  Padding(
                                    padding: const EdgeInsets.all(16),
                                    child: PlanDraftCard(
                                      draft: planDraft,
                                      onConfirm: state.confirmPlanDraft,
                                      onDiscard: state.discardPlanDraft,
                                    ),
                                  ),
                                SizedBox(
                                  height: MediaQuery.of(context).size.height * 0.35,
                                  child: TodayEmpty(onGoCompanion: () => state.goToTab(0)),
                                ),
                              ],
                            )
                          : ListView(
                              children: [
                                TodayHeader(
                                  streakDays: summary?['streak_days'] as int? ?? 0,
                                  onReview: () => _loadAndReview(state),
                                ),
                                TodayHeroCard(
                                  openCount: openCount,
                                  done: done,
                                  total: total,
                                  wakeName: wakeName,
                                ),
                                RoutineChips(
                                  busy: state.loading,
                                  onSelect: (t) => _suggestDay(state, template: t),
                                ),
                                Padding(
                                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
                                  child: OutlinedButton.icon(
                                    onPressed: state.loading ? null : () => _suggestDay(state),
                                    icon: state.loading
                                        ? const SizedBox(
                                            width: 16,
                                            height: 16,
                                            child: CircularProgressIndicator(strokeWidth: 2),
                                          )
                                        : const Icon(Icons.auto_awesome_outlined),
                                    label: const Text('Suggest for me'),
                                  ),
                                ),
                                if (planDraft != null)
                                  Padding(
                                    padding: const EdgeInsets.symmetric(horizontal: 16),
                                    child: PlanDraftCard(
                                      draft: planDraft,
                                      onConfirm: state.confirmPlanDraft,
                                      onDiscard: state.discardPlanDraft,
                                    ),
                                  ),
                                if (upNext != null)
                                  UpNextCard(
                                    task: upNext,
                                    onStartFocus: () => state.startFocus(upNext),
                                    onDone: () => state.completeTask(upNext['id'] as int),
                                    onBreakdown: () => state.breakdownTask(upNext['id'] as int),
                                    onEdit: () => _editTask(state, upNext),
                                  ),
                                if (now.isNotEmpty) ...[
                                  _sectionLabel('Now'),
                                  ...now.map((t) => TimelineTaskTile(
                                        task: t,
                                        onTap: () => _editTask(state, t),
                                        onComplete: () => state.completeTask(t['id'] as int),
                                      )),
                                ],
                                if (upcoming.isNotEmpty) ...[
                                  _sectionLabel('Upcoming'),
                                  PriorityLanes(
                                    tasks: upcoming,
                                    onComplete: (id) => state.completeTask(id),
                                    onTap: (t) => _editTask(state, t),
                                    onReorderLane: (priority, oldIndex, newIndex) =>
                                        state.reorderUpcomingLane(upcoming, priority, oldIndex, newIndex),
                                  ),
                                ],
                                if (completed.isNotEmpty) ...[
                                  ListTile(
                                    title: Text('Completed (${completed.length})'),
                                    trailing: Icon(_completedExpanded ? Icons.expand_less : Icons.expand_more),
                                    onTap: () => setState(() => _completedExpanded = !_completedExpanded),
                                  ),
                                  if (_completedExpanded)
                                    ...completed.map((t) => TimelineTaskTile(task: t, dimmed: true)),
                                ],
                                const SizedBox(height: 80),
                              ],
                            ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _sectionLabel(String text) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
      child: Text(text, style: TextStyle(color: Colors.white.withValues(alpha: 0.5), fontWeight: FontWeight.w600)),
    );
  }

  Future<void> _loadAndReview(AppState state) async {
    await state.loadEveningPayload();
    if (mounted) _openReview(state);
  }
}
