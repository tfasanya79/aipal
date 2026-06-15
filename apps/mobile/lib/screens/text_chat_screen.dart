import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../providers/app_state.dart';
import '../widgets/plan_draft_card.dart';

class TextChatScreen extends StatefulWidget {
  const TextChatScreen({super.key});

  @override
  State<TextChatScreen> createState() => _TextChatScreenState();
}

class _TextChatScreenState extends State<TextChatScreen> {
  final _controller = TextEditingController();
  final _messages = <Map<String, dynamic>>[];
  final _sessionId = const Uuid().v4();
  Map<String, dynamic>? _planDraft;

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    setState(() {
      _messages.add({'role': 'user', 'text': text});
      _controller.clear();
    });
    final state = context.read<AppState>();
    final res = await state.sendTextTurn(text, sessionId: _sessionId);
    setState(() {
      _messages.add({
        'role': 'assistant',
        'text': res['reply'] as String? ?? '...',
        'tool_actions': res['tool_actions'],
      });
      _planDraft = res['plan_draft'] as Map<String, dynamic>?;
    });
  }

  Future<void> _confirmPlan() async {
    final state = context.read<AppState>();
    await state.confirmPlanDraft();
    if (mounted) {
      setState(() => _planDraft = null);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Added to Today')),
      );
    }
  }

  Future<void> _discardPlan() async {
    await context.read<AppState>().discardPlanDraft();
    if (mounted) setState(() => _planDraft = null);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Text mode')),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _messages.length + (_planDraft != null ? 1 : 0),
              itemBuilder: (context, i) {
                if (_planDraft != null && i == _messages.length) {
                  return PlanDraftCard(
                    draft: _planDraft!,
                    onConfirm: _confirmPlan,
                    onDiscard: _discardPlan,
                  );
                }
                final m = _messages[i];
                final isUser = m['role'] == 'user';
                final tools = m['tool_actions'] as List?;
                return Column(
                  crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
                  children: [
                    Align(
                      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                      child: Container(
                        margin: const EdgeInsets.only(bottom: 4),
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                        decoration: BoxDecoration(
                          color: isUser
                              ? const Color(0xFF21262D)
                              : Theme.of(context).colorScheme.primary.withValues(alpha: 0.25),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Text(m['text'] as String),
                      ),
                    ),
                    if (tools != null && tools.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8, left: 4),
                        child: Text(
                          tools.join(' · '),
                          style: TextStyle(fontSize: 11, color: Colors.white.withValues(alpha: 0.5)),
                        ),
                      ),
                  ],
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    decoration: const InputDecoration(hintText: 'Type a message...'),
                    onSubmitted: (_) => _send(),
                  ),
                ),
                IconButton(onPressed: _send, icon: const Icon(Icons.send)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
