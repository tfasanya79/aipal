#!/usr/bin/env bash
set -euo pipefail
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/android-sdk}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"
export PATH="/opt/flutter/bin:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:${PATH}"
cd "$(dirname "$0")/../apps/mobile"
if ! command -v flutter >/dev/null; then
  echo "Flutter SDK required. Install from https://flutter.dev"
  exit 1
fi
flutter pub get
flutter build appbundle --release \
  --dart-define=API_BASE_URL="${API_BASE_URL:-https://43.160.220.9.sslip.io/api/v2}"
echo "AAB: build/app/outputs/bundle/release/app-release.aab"
echo "Upload to Play Internal — versionCode 6, versionName 2.0.0"
