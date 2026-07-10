import 'dart:async';

import 'microphone_owner.dart';

class MicrophoneManager {
  MicrophoneManager._();

  static final MicrophoneManager instance = MicrophoneManager._();

  MicrophoneOwner? _owner;
  DateTime? _acquiredAt;
  Completer<void>? _releaseSignal;

  MicrophoneOwner? get currentOwner => _owner;
  String get currentOwnerLabel => _owner?.name ?? 'none';
  DateTime? get acquiredAt => _acquiredAt;

  Future<bool> acquire(
    MicrophoneOwner owner, {
    Duration timeout = const Duration(seconds: 2),
  }) async {
    if (_owner == null || _owner == owner) {
      _owner = owner;
      _acquiredAt = DateTime.now().toUtc();
      return true;
    }

    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      final remaining = deadline.difference(DateTime.now());
      final signal = _releaseSignal ??= Completer<void>();
      try {
        await signal.future.timeout(remaining);
      } catch (_) {
        return false;
      }
      if (_owner == null || _owner == owner) {
        _owner = owner;
        _acquiredAt = DateTime.now().toUtc();
        return true;
      }
    }
    return false;
  }

  void release(MicrophoneOwner owner) {
    if (_owner != owner) return;
    _owner = null;
    _acquiredAt = null;
    if (_releaseSignal != null && !_releaseSignal!.isCompleted) {
      _releaseSignal!.complete();
    }
    _releaseSignal = null;
  }
}
