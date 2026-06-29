import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:uuid/uuid.dart';

import '../providers/app_state.dart';
import '../services/compose_message_draft.dart';
import '../widgets/plan_draft_card.dart';

class TextChatScreen extends StatefulWidget {
  const TextChatScreen({super.key});

  @override
  State<TextChatScreen> createState() => _TextChatScreenState();
}

class _TextChatScreenState extends State<TextChatScreen> {
  final _controller = TextEditingController();
  final _draftBodyController = TextEditingController();
  final _messages = <Map<String, dynamic>>[];
  final _sessionId = const Uuid().v4();
  Map<String, dynamic>? _planDraft;
  ComposeChannel? _draftChannel;
  bool _draftLoading = false;

  @override
  void dispose() {
    _controller.dispose();
    _draftBodyController.dispose();
    super.dispose();
  }

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

  Future<void> _showComposeDraftDialog() async {
    final intentController = TextEditingController();
    ComposeChannel channel = ComposeChannel.sms;
    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Compose message draft'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<ComposeChannel>(
                value: channel,
                decoration: const InputDecoration(labelText: 'Type'),
                items: const [
                  DropdownMenuItem(value: ComposeChannel.sms, child: Text('SMS')),
                  DropdownMenuItem(value: ComposeChannel.email, child: Text('Email')),
                ],
                onChanged: (value) {
                  if (value == null) return;
                  setDialogState(() => channel = value);
                },
              ),
              const SizedBox(height: 12),
              TextField(
                controller: intentController,
                autofocus: true,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'What do you want to say?',
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () async {
                final intent = intentController.text.trim();
                if (intent.isEmpty) return;
                Navigator.of(context).pop();
                await _generateComposeDraft(intent, channel);
              },
              child: const Text('Draft'),
            ),
          ],
        ),
      ),
    );
    intentController.dispose();
  }

  Future<void> _generateComposeDraft(String intent, ComposeChannel channel) async {
    setState(() => _draftLoading = true);
    try {
      final state = context.read<AppState>();
      final res = await state.sendTextTurn(
        buildComposeDraftPrompt(channel: channel, intent: intent),
        sessionId: _sessionId,
      );
      final draft = normalizeDraftText(res['reply'] as String? ?? '');
      if (!mounted) return;
      setState(() {
        _draftBodyController.text = draft;
        _draftChannel = channel;
      });
    } finally {
      if (mounted) setState(() => _draftLoading = false);
    }
  }

  Future<void> _copyDraft() async {
    final text = _draftBodyController.text.trim();
    if (text.isEmpty) return;
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Draft copied to clipboard.')),
    );
  }

  Future<void> _openComposeApp() async {
    final text = _draftBodyController.text.trim();
    final channel = _draftChannel;
    if (text.isEmpty || channel == null) return;
    final uri = buildComposeUri(channel: channel, body: text);
    final errorMessage = 'Could not open ${composeChannelLabel(channel)} app.';
    try {
      final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!launched && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(errorMessage)),
        );
      }
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(errorMessage)),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Text mode'),
        actions: [
          TextButton.icon(
            onPressed: _draftLoading ? null : _showComposeDraftDialog,
            icon: const Icon(Icons.edit_note),
            label: const Text('Compose'),
          ),
          const SizedBox(width: 8),
        ],
      ),
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
          if (_draftLoading) const LinearProgressIndicator(minHeight: 2),
          if (_draftChannel != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 6, 12, 0),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${composeChannelLabel(_draftChannel!)} draft',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Review/edit, then send manually.',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      const SizedBox(height: 8),
                      TextField(
                        controller: _draftBodyController,
                        minLines: 3,
                        maxLines: 8,
                        decoration: const InputDecoration(
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          OutlinedButton.icon(
                            onPressed: _copyDraft,
                            icon: const Icon(Icons.copy),
                            label: const Text('Copy'),
                          ),
                          const SizedBox(width: 8),
                          FilledButton.icon(
                            onPressed: _openComposeApp,
                            icon: const Icon(Icons.open_in_new),
                            label: Text('Open ${composeChannelLabel(_draftChannel!)}'),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
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
