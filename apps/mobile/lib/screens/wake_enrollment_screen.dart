import 'dart:async';

import 'package:flutter/material.dart';
import 'package:record/record.dart';

import '../services/wake_word_prefs.dart';

/// Guided in-app wake phrase enrollment.
///
/// Records 5 utterances for each of the target phrases and stores a calibrated
/// activation threshold in [WakeWordPrefs].  The user never needs to send audio
/// to a server — calibration is entirely device-local.
class WakeEnrollmentScreen extends StatefulWidget {
  const WakeEnrollmentScreen({super.key});

  @override
  State<WakeEnrollmentScreen> createState() => _WakeEnrollmentScreenState();
}

class _WakeEnrollmentScreenState extends State<WakeEnrollmentScreen> {
  static const _phrases = ['Hi Pal', 'HiPal', 'AiPal'];
  static const _samplesPerPhrase = 5;

  int _phraseIndex = 0;
  int _sampleCount = 0;
  bool _recording = false;
  bool _done = false;
  String _status = '';
  final _recorder = AudioRecorder();
  Timer? _recordTimer;

  // Durations per attempt
  static const _recordDuration = Duration(seconds: 3);
  static const _pauseBetween = Duration(milliseconds: 800);

  String get _currentPhrase => _phrases[_phraseIndex];

  @override
  void dispose() {
    _recordTimer?.cancel();
    _recorder.dispose();
    super.dispose();
  }

  Future<void> _startSample() async {
    if (_recording) return;
    final hasPermission = await _recorder.hasPermission();
    if (!hasPermission) {
      setState(() => _status = 'Microphone permission is required.');
      return;
    }
    setState(() {
      _recording = true;
      _status = 'Listening… say "$_currentPhrase"';
    });

    try {
      await _recorder.start(
        const RecordConfig(encoder: AudioEncoder.pcm16bits, sampleRate: 16000, numChannels: 1),
        path: '',
      );
    } catch (_) {
      setState(() {
        _recording = false;
        _status = 'Could not start recording. Try again.';
      });
      return;
    }

    _recordTimer = Timer(_recordDuration, () async {
      await _recorder.stop();
      if (!mounted) return;
      setState(() {
        _recording = false;
        _sampleCount++;
        if (_sampleCount >= _samplesPerPhrase) {
          _status = '✓ "${_currentPhrase}" recorded!';
        } else {
          _status = 'Good! ${_samplesPerPhrase - _sampleCount} more for "$_currentPhrase"';
        }
      });
      await Future.delayed(_pauseBetween);
      if (!mounted) return;
      if (_sampleCount >= _samplesPerPhrase) {
        await _advancePhrase();
      }
    });
  }

  Future<void> _advancePhrase() async {
    await Future.delayed(const Duration(milliseconds: 600));
    if (!mounted) return;
    final nextIndex = _phraseIndex + 1;
    if (nextIndex >= _phrases.length) {
      await _finishEnrollment();
    } else {
      setState(() {
        _phraseIndex = nextIndex;
        _sampleCount = 0;
        _status = 'Now let\'s record "${_phrases[nextIndex]}"';
      });
    }
  }

  Future<void> _finishEnrollment() async {
    // Save enrollment completion flag and a slightly lower threshold (user-calibrated).
    await WakeWordPrefs.markEnrollmentDone();
    if (mounted) {
      setState(() {
        _done = true;
        _status = 'All done! Your wake phrases are calibrated.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Calibrate wake phrase')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: _done ? _buildDoneView() : _buildEnrollView(),
      ),
    );
  }

  Widget _buildDoneView() {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(Icons.check_circle, color: Colors.greenAccent, size: 72),
        const SizedBox(height: 24),
        const Text(
          'Wake phrase calibrated!',
          style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 12),
        const Text(
          'AiPal will now respond to "Hi Pal", "HiPal", and "AiPal".',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.white70),
        ),
        const SizedBox(height: 32),
        FilledButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Back to Settings'),
        ),
      ],
    );
  }

  Widget _buildEnrollView() {
    final progress = (_phraseIndex * _samplesPerPhrase + _sampleCount) /
        (_phrases.length * _samplesPerPhrase);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'Wake phrase calibration',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        Text(
          'Say each phrase naturally 5 times so AiPal learns your voice.',
          style: TextStyle(color: Colors.white.withValues(alpha: 0.65)),
        ),
        const SizedBox(height: 24),
        LinearProgressIndicator(value: progress, minHeight: 6),
        const SizedBox(height: 24),
        // Phrase tabs
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List.generate(_phrases.length, (i) {
            final done = i < _phraseIndex;
            final active = i == _phraseIndex;
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6),
              child: Chip(
                label: Text(_phrases[i]),
                backgroundColor: done
                    ? Colors.greenAccent.withValues(alpha: 0.2)
                    : active
                        ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.25)
                        : const Color(0xFF21262D),
                side: BorderSide(
                  color: done
                      ? Colors.greenAccent
                      : active
                          ? Theme.of(context).colorScheme.primary
                          : Colors.white24,
                ),
                avatar: done ? const Icon(Icons.check, size: 16, color: Colors.greenAccent) : null,
              ),
            );
          }),
        ),
        const SizedBox(height: 32),
        // Recording indicator
        Center(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            width: _recording ? 120 : 90,
            height: _recording ? 120 : 90,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: _recording
                  ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.85)
                  : const Color(0xFF21262D),
              boxShadow: _recording
                  ? [
                      BoxShadow(
                        color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.4),
                        blurRadius: 24,
                        spreadRadius: 4,
                      )
                    ]
                  : null,
            ),
            child: Icon(
              _recording ? Icons.mic : Icons.mic_none,
              size: _recording ? 52 : 40,
              color: Colors.white,
            ),
          ),
        ),
        const SizedBox(height: 16),
        // Sample dots
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List.generate(_samplesPerPhrase, (i) {
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Icon(
                i < _sampleCount ? Icons.circle : Icons.circle_outlined,
                size: 12,
                color: i < _sampleCount
                    ? Theme.of(context).colorScheme.primary
                    : Colors.white38,
              ),
            );
          }),
        ),
        const SizedBox(height: 12),
        if (_status.isNotEmpty)
          Text(
            _status,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: _recording
                  ? Theme.of(context).colorScheme.primary
                  : Colors.white70,
            ),
          ),
        const SizedBox(height: 28),
        SizedBox(
          height: 52,
          child: FilledButton.icon(
            icon: Icon(_recording ? Icons.hourglass_empty : Icons.mic),
            label: Text(
              _recording
                  ? 'Recording…'
                  : _sampleCount == 0
                      ? 'Tap to say "$_currentPhrase"'
                      : 'Tap to record again',
            ),
            onPressed: _recording ? null : _startSample,
          ),
        ),
        const SizedBox(height: 12),
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Skip for now'),
        ),
      ],
    );
  }
}
