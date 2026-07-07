import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import '../services/social_auth_service.dart';
import '../widgets/aipal_logo.dart';
import '../services/device_timezone.dart';
import '../services/notification_service.dart';
import 'home_shell.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key, this.continueProfile = false});

  final bool continueProfile;

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _email = TextEditingController();
  final _wakeName = TextEditingController();
  final _about = TextEditingController();
  int _step = 0;
  String? _error;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    if (widget.continueProfile) _step = 1;
  }

  Future<void> _handleSocialAuth(
    Future<Map<String, dynamic>?> Function() signIn,
  ) async {
    final state = context.read<AppState>();
    try {
      final result = await signIn();
      if (result == null) return;
      await state.setTokenFromSocialAuth(result);
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushReplacement(MaterialPageRoute(builder: (_) => const HomeShell()));
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  Future<void> _finish() async {
    if (_submitting) return;
    final state = context.read<AppState>();
    setState(() {
      _error = null;
      _submitting = true;
    });
    try {
      final profilePayload = {
        'wake_name': _wakeName.text.trim().isEmpty
            ? 'friend'
            : _wakeName.text.trim(),
        'display_name': _wakeName.text.trim(),
        'about_me': _about.text.trim(),
        'timezone': await deviceIanaTimezone(),
        'morning_brief_at': '08:00',
        'evening_recap_at': '20:00',
      };
      final result = await state.completeOnboarding(
        continueProfile: widget.continueProfile,
        email: _email.text.trim(),
        profileData: profilePayload,
      );
      if (!mounted) return;
      if (!result.proceedToHome) {
        setState(() {
          _error =
              result.errorMessage ??
              'Could not finish setup right now. Please try again.';
        });
        return;
      }
      try {
        await NotificationService.instance.scheduleMorningBrief(
          hour: 8,
          minute: 0,
        );
        await NotificationService.instance.scheduleEveningRecap(
          hour: 20,
          minute: 0,
        );
      } catch (_) {
        // Notifications are optional at onboarding; don't block entry.
      }
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushReplacement(MaterialPageRoute(builder: (_) => const HomeShell()));
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = 'Could not finish setup right now. Please try again.';
      });
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 24),
              if (_step == 0) ...[
                const Center(child: AiPalOrbMark(size: 56)),
                const SizedBox(height: 16),
                const Center(child: AiPalLogo(size: 36)),
              ],
              const SizedBox(height: 12),
              Text(
                _step == 0 ? 'Welcome' : 'Tell me about you',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 8),
              Text(
                'Not a substitute for emergency or professional care.',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.6),
                  fontSize: 13,
                ),
              ),
              const SizedBox(height: 32),
              if (_step == 0 && !widget.continueProfile) ...[
                ElevatedButton.icon(
                  onPressed: _submitting
                      ? null
                      : () => _handleSocialAuth(
                          () => SocialAuthService.signInWithGoogle(null),
                        ),
                  icon: const Icon(Icons.login),
                  label: const Text('Continue with Google'),
                ),
                if (Platform.isIOS) ...[
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: _submitting
                        ? null
                        : () => _handleSocialAuth(
                            () => SocialAuthService.signInWithApple(null),
                          ),
                    icon: const Icon(Icons.apple),
                    label: const Text('Continue with Apple'),
                  ),
                ],
                const SizedBox(height: 16),
                Row(
                  children: [
                    const Expanded(child: Divider()),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                      child: Text(
                        'or',
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.5),
                        ),
                      ),
                    ),
                    const Expanded(child: Divider()),
                  ],
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _email,
                  enabled: !_submitting,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(
                    labelText: 'Email for magic link',
                  ),
                ),
              ] else ...[
                TextField(
                  controller: _wakeName,
                  enabled: !_submitting,
                  decoration: const InputDecoration(
                    labelText: 'What should I call you?',
                  ),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _about,
                  enabled: !_submitting,
                  maxLines: 3,
                  decoration: const InputDecoration(
                    labelText: 'A bit about yourself (optional)',
                  ),
                ),
              ],
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(_error!, style: const TextStyle(color: Colors.redAccent)),
              ],
              const Spacer(),
              FilledButton(
                onPressed: _submitting
                    ? null
                    : () {
                        if (_step == 0 && !widget.continueProfile) {
                          final email = _email.text.trim();
                          if (email.isEmpty || !email.contains('@')) {
                            setState(
                              () => _error = 'Enter a valid email address',
                            );
                            return;
                          }
                          setState(() {
                            _error = null;
                            _step = 1;
                          });
                        } else {
                          _finish();
                        }
                      },
                child: _submitting
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(
                        _step == 0 && !widget.continueProfile
                            ? 'Continue'
                            : 'Start with AiPal',
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
