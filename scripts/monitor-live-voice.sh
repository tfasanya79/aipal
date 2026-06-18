#!/usr/bin/env bash
# Tail half-duplex Live voice and session observability logs (run on the VM).
# Usage: ./scripts/monitor-live-voice.sh
set -euo pipefail

echo "Monitoring AiPal voice + session logs (Ctrl+C to stop)…"
echo "Look for: audio_turn_complete, live_start, segment_upload, turn_complete, wake_detected, stt_empty"
echo ""

sudo journalctl -u aipal-v2.service -f --no-pager 2>&1 \
  | grep --line-buffered -iE 'audio_turn|session_events|aipal\.turn|live_start|segment_upload|turn_complete|wake_detected|stt_empty|transcript|error|exception'
