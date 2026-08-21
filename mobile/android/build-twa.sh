#!/usr/bin/env bash
# Compile the BadgeDay Play TWA from mobile/android/twa-manifest.json.
#
# Unsigned / skip-signing on purpose: this is a first compile, not a store submit.
# Play Billing stays off. The application id stays com.badgeday.app. This script
# never calls bubblewrap play, never creates IAP, and never writes a keystore.
#
# Usage (from anywhere):
#   mobile/android/build-twa.sh
#
# Optional environment:
#   ANDROID_SDK_ROOT     SDK install root (default: $HOME/.android-sdk)
#   TWA_JDK_PATH         JDK 17 home (auto-detected when unset)
#   TWA_ARTIFACT_DIR     where to copy the AAB/APK (default: $PWD/artifacts/twa)
#   TWA_SKIP_TOOLCHAIN=1 skip JDK / SDK / bubblewrap installs (CI with preinstalled tools)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ANDROID_DIR="$REPO_ROOT/mobile/android"
MANIFEST="$ANDROID_DIR/twa-manifest.json"
EXPECTED_PACKAGE='com.badgeday.app'
# Bubblewrap 1.24+ pins this build-tools version in AndroidSdkTools.ts.
BUILD_TOOLS_VERSION='36.1.0'
COMPILE_SDK='36'
# Current "Command line tools only" zip on developer.android.com (Linux).
CMDLINE_TOOLS_URL='https://dl.google.com/android/repository/commandlinetools-linux-15859902_latest.zip'
CMDLINE_TOOLS_SHA256='4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583'
BUBBLEWRAP_PKG='@bubblewrap/cli@1.25.0'

ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/.android-sdk}"
TWA_ARTIFACT_DIR="${TWA_ARTIFACT_DIR:-$REPO_ROOT/artifacts/twa}"
TWA_SKIP_TOOLCHAIN="${TWA_SKIP_TOOLCHAIN:-0}"
TWA_NPM_PREFIX="${TWA_NPM_PREFIX:-$HOME/.cache/badgeday-twa}"
BUBBLEWRAP=""

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: required command not found: $1" >&2
    exit 1
  }
}

# Refuse to compile if the committed answer set drifted. Bubblewrap update
# --skipVersionUpgrade does not rewrite twa-manifest.json; this is belt and braces.
assert_twa_guardrails() {
  python3 - "$MANIFEST" "$EXPECTED_PACKAGE" <<'PY'
import json, sys
path, expected = sys.argv[1], sys.argv[2]
manifest = json.loads(open(path, encoding="utf-8").read())
errors = []
if manifest.get("packageId") != expected:
    errors.append(f"packageId is {manifest.get('packageId')!r}, expected {expected!r}")
billing = (manifest.get("features") or {}).get("playBilling") or {}
if billing.get("enabled") is not False:
    errors.append(f"features.playBilling.enabled is {billing.get('enabled')!r}, expected False")
if errors:
    print("TWA guardrail failed:", file=sys.stderr)
    for item in errors:
        print(f"  - {item}", file=sys.stderr)
    sys.exit(1)
print(f"TWA guardrails ok: packageId={expected} playBilling=false")
PY
}

find_jdk17() {
  if [ -n "${TWA_JDK_PATH:-}" ]; then
    printf '%s\n' "$TWA_JDK_PATH"
    return
  fi
  local candidate
  for candidate in \
    /usr/lib/jvm/java-17-openjdk-amd64 \
    /usr/lib/jvm/java-17-openjdk-arm64 \
    /usr/lib/jvm/temurin-17-jdk-amd64 \
    "${JAVA_HOME:-}"; do
    if [ -n "$candidate" ] && [ -f "$candidate/release" ] \
      && grep -q 'JAVA_VERSION="17\.' "$candidate/release"; then
      printf '%s\n' "$candidate"
      return
    fi
  done
  return 1
}

install_jdk17() {
  if find_jdk17 >/dev/null; then
    return
  fi
  if [ "$TWA_SKIP_TOOLCHAIN" = 1 ]; then
    echo "error: JDK 17 not found and TWA_SKIP_TOOLCHAIN=1" >&2
    exit 1
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    echo "error: cannot install openjdk-17-jdk (no sudo). Set TWA_JDK_PATH to a JDK 17 home." >&2
    exit 1
  fi
  sudo apt-get update -qq
  sudo apt-get install -y -qq openjdk-17-jdk
  find_jdk17 >/dev/null || {
    echo "error: openjdk-17-jdk installed but JAVA_VERSION=17 was not found under /usr/lib/jvm" >&2
    exit 1
  }
}

# Bubblewrap looks for sdkmanager at $ANDROID_SDK_ROOT/bin or $ANDROID_SDK_ROOT/tools/bin,
# not the modern cmdline-tools/latest/bin layout. Keep a real bin/ at the SDK root.
install_android_sdk() {
  mkdir -p "$ANDROID_SDK_ROOT"
  local sdkmanager=""
  if [ -x "$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" ]; then
    # Directory symlink so sdkmanager's ../lib resolution still works.
    ln -sfn cmdline-tools/latest/bin "$ANDROID_SDK_ROOT/bin"
    sdkmanager="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager"
  elif [ -x "$ANDROID_SDK_ROOT/bin/sdkmanager" ]; then
    sdkmanager="$ANDROID_SDK_ROOT/bin/sdkmanager"
  fi

  if [ -z "$sdkmanager" ]; then
    if [ "$TWA_SKIP_TOOLCHAIN" = 1 ]; then
      echo "error: Android SDK not found at $ANDROID_SDK_ROOT and TWA_SKIP_TOOLCHAIN=1" >&2
      exit 1
    fi
    require_cmd curl
    require_cmd unzip
    require_cmd sha256sum
    local zip="$ANDROID_SDK_ROOT/commandlinetools-linux.zip"
    echo "Downloading Android command-line tools…"
    curl -fsSL "$CMDLINE_TOOLS_URL" -o "$zip"
    echo "$CMDLINE_TOOLS_SHA256  $zip" | sha256sum -c -
    rm -rf "$ANDROID_SDK_ROOT/cmdline-tools"
    mkdir -p "$ANDROID_SDK_ROOT/cmdline-tools"
    unzip -q "$zip" -d "$ANDROID_SDK_ROOT/cmdline-tools"
    # Zip root is cmdline-tools/{bin,lib,…}; sdkmanager wants …/cmdline-tools/latest/bin.
    mv "$ANDROID_SDK_ROOT/cmdline-tools/cmdline-tools" "$ANDROID_SDK_ROOT/cmdline-tools/latest"
    rm -f "$zip"
    ln -sfn cmdline-tools/latest/bin "$ANDROID_SDK_ROOT/bin"
    sdkmanager="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager"
  fi

  # sdkmanager is a wrapper that lives next to lib/; calling the symlink at
  # $SDK/bin/sdkmanager fails because it looks for ../lib. Always invoke the real path.
  local real_sdkmanager="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager"
  if [ ! -x "$real_sdkmanager" ]; then
    echo "error: sdkmanager missing at $real_sdkmanager" >&2
    exit 1
  fi

  mkdir -p "$ANDROID_SDK_ROOT/licenses"
  # Standard Android SDK license acceptance id. Not a secret.
  printf '%s\n' '24333f8a63b6825ea9c5514f83c2829b004d1fee' \
    > "$ANDROID_SDK_ROOT/licenses/android-sdk-license"
  printf '%s\n' '84831b9409646161bf1c37d8b451e888044d742a' \
    > "$ANDROID_SDK_ROOT/licenses/android-sdk-preview-license"

  if [ "$TWA_SKIP_TOOLCHAIN" != 1 ]; then
    echo "Installing Android SDK packages (platforms;$COMPILE_SDK, build-tools;$BUILD_TOOLS_VERSION)…"
    "$real_sdkmanager" --sdk_root="$ANDROID_SDK_ROOT" --install \
      "platform-tools" \
      "platforms;android-${COMPILE_SDK}" \
      "build-tools;${BUILD_TOOLS_VERSION}"
  fi

  [ -d "$ANDROID_SDK_ROOT/build-tools/$BUILD_TOOLS_VERSION" ] || {
    echo "error: build-tools $BUILD_TOOLS_VERSION missing under $ANDROID_SDK_ROOT" >&2
    exit 1
  }
  [ -d "$ANDROID_SDK_ROOT/platforms/android-${COMPILE_SDK}" ] || {
    echo "error: platforms;android-${COMPILE_SDK} missing under $ANDROID_SDK_ROOT" >&2
    exit 1
  }
}

install_bubblewrap() {
  # User-local prefix: `npm install -g` needs write access to the global
  # node_modules and this environment's npm prefix is not writable.
  BUBBLEWRAP="$TWA_NPM_PREFIX/node_modules/.bin/bubblewrap"
  if [ -x "$BUBBLEWRAP" ]; then
    return
  fi
  if [ "$TWA_SKIP_TOOLCHAIN" = 1 ]; then
    if command -v bubblewrap >/dev/null 2>&1; then
      BUBBLEWRAP="$(command -v bubblewrap)"
      return
    fi
    echo "error: $BUBBLEWRAP_PKG not installed and TWA_SKIP_TOOLCHAIN=1" >&2
    exit 1
  fi
  require_cmd npm
  mkdir -p "$TWA_NPM_PREFIX"
  npm install --prefix "$TWA_NPM_PREFIX" "$BUBBLEWRAP_PKG"
  [ -x "$BUBBLEWRAP" ] || {
    echo "error: npm install --prefix $TWA_NPM_PREFIX $BUBBLEWRAP_PKG did not produce bubblewrap" >&2
    exit 1
  }
}

write_bubblewrap_config() {
  local jdk_path="$1"
  mkdir -p "$HOME/.bubblewrap"
  # Paths only. No keystore material.
  python3 - "$HOME/.bubblewrap/config.json" "$jdk_path" "$ANDROID_SDK_ROOT" <<'PY'
import json, sys
path, jdk, sdk = sys.argv[1], sys.argv[2], sys.argv[3]
json.dump({"jdkPath": jdk, "androidSdkPath": sdk}, open(path, "w"), indent=2)
open(path, "a").write("\n")
PY
}

assert_generated_project() {
  local gradle="$ANDROID_DIR/app/build.gradle"
  [ -f "$gradle" ] || {
    echo "error: generated $gradle missing" >&2
    exit 1
  }
  python3 - "$gradle" "$EXPECTED_PACKAGE" <<'PY'
import sys
gradle, expected = open(sys.argv[1], encoding="utf-8").read(), sys.argv[2]
errors = []
if f'applicationId "{expected}"' not in gradle and f"applicationId '{expected}'" not in gradle:
    errors.append(f"generated app/build.gradle does not set applicationId {expected}")
billing_needles = (
    "play-services-billing",
    "billing.Billing",
    "DigitalGoods",
    "com.android.billingclient",
)
for needle in billing_needles:
    if needle.lower() in gradle.lower():
        errors.append(f"generated app/build.gradle mentions Play Billing ({needle})")
if errors:
    print("Generated project guardrail failed:", file=sys.stderr)
    for item in errors:
        print(f"  - {item}", file=sys.stderr)
    sys.exit(1)
print("Generated project ok: applicationId set, no Play Billing dependency")
PY
}

copy_artifacts() {
  mkdir -p "$TWA_ARTIFACT_DIR"
  local copied=0
  local name
  for name in \
    app-release-unsigned.apk \
    app-release-bundle.aab \
    app-release-unsigned.aab \
    app-release.aab \
    app-release-signed.apk; do
    if [ -f "$ANDROID_DIR/$name" ]; then
      cp -f "$ANDROID_DIR/$name" "$TWA_ARTIFACT_DIR/$name"
      echo "copied $name -> $TWA_ARTIFACT_DIR/$name"
      copied=1
    fi
  done
  # Gradle default outputs if bubblewrap left them in app/build.
  local extra
  while IFS= read -r extra; do
    name="$(basename "$extra")"
    cp -f "$extra" "$TWA_ARTIFACT_DIR/$name"
    echo "copied $extra -> $TWA_ARTIFACT_DIR/$name"
    copied=1
  done < <(find "$ANDROID_DIR/app/build/outputs" -type f \( -name '*.apk' -o -name '*.aab' \) 2>/dev/null || true)
  if [ "$copied" -eq 0 ]; then
    echo "error: build finished but no APK/AAB was found under $ANDROID_DIR" >&2
    exit 1
  fi
}

main() {
  [ -f "$MANIFEST" ] || {
    echo "error: missing $MANIFEST" >&2
    exit 1
  }
  assert_twa_guardrails
  require_cmd python3
  require_cmd npm

  install_jdk17
  local jdk_path
  jdk_path="$(find_jdk17)"
  install_android_sdk
  install_bubblewrap
  write_bubblewrap_config "$jdk_path"

  export JAVA_HOME="$jdk_path"
  export ANDROID_HOME="$ANDROID_SDK_ROOT"
  export ANDROID_SDK_ROOT
  export PATH="$jdk_path/bin:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$PATH"

  echo "Using JDK $jdk_path"
  echo "Using Android SDK $ANDROID_SDK_ROOT"
  echo "Using Bubblewrap $BUBBLEWRAP"
  "$BUBBLEWRAP" --version || true

  # Regenerates mobile/android/app (gitignored) from the committed twa-manifest.json
  # without bumping appVersionCode and without rewriting the manifest.
  (
    cd "$ANDROID_DIR"
    "$BUBBLEWRAP" update --skipVersionUpgrade --manifest="$MANIFEST"
  )
  assert_twa_guardrails
  assert_generated_project

  (
    cd "$ANDROID_DIR"
    "$BUBBLEWRAP" build --skipPwaValidation --skipSigning --manifest="$MANIFEST"
  )
  assert_twa_guardrails
  copy_artifacts
  echo "TWA compile finished. Artifacts in $TWA_ARTIFACT_DIR"
}

main "$@"
