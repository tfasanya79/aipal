import 'package:aipal/services/voice/microphone_manager.dart';
import 'package:aipal/services/voice/microphone_owner.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('microphone manager grants and releases ownership', () async {
    final manager = MicrophoneManager.instance;
    manager.release(MicrophoneOwner.liveVoiceLoop);
    manager.release(MicrophoneOwner.wakeWordEngine);
    manager.release(MicrophoneOwner.wakeEnrollment);

    final acquired = await manager.acquire(MicrophoneOwner.liveVoiceLoop);
    expect(acquired, isTrue);
    expect(manager.currentOwner, MicrophoneOwner.liveVoiceLoop);

    manager.release(MicrophoneOwner.liveVoiceLoop);
    expect(manager.currentOwner, isNull);
  });

  test('microphone manager blocks competing owner until release', () async {
    final manager = MicrophoneManager.instance;
    manager.release(MicrophoneOwner.liveVoiceLoop);
    manager.release(MicrophoneOwner.wakeWordEngine);

    expect(await manager.acquire(MicrophoneOwner.wakeWordEngine), isTrue);

    final blocked = await manager.acquire(
      MicrophoneOwner.liveVoiceLoop,
      timeout: const Duration(milliseconds: 20),
    );
    expect(blocked, isFalse);

    manager.release(MicrophoneOwner.wakeWordEngine);
    expect(await manager.acquire(MicrophoneOwner.liveVoiceLoop), isTrue);
    manager.release(MicrophoneOwner.liveVoiceLoop);
  });
}
