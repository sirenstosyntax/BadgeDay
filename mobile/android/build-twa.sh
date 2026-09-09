#!/usr/bin/env bash
# Compile the BadgeDay Play TWA from mobile/android/twa-manifest.json.
#
# Play Billing is on: the generated AAB must carry BILLING and the Digital
# Goods / PaymentActivity wiring so a SKU can be attached later. This script
# never invents an in-app product, never calls `bubblewrap play`, and never
# writes a keystore unless CI/env already supplied one.
#
# Signing (optional): if TWA_KEYSTORE_BASE64, TWA_KEYSTORE_PASSWORD,
# TWA_KEY_ALIAS and TWA_KEY_PASSWORD are all set, the AAB is signed with that
# upload key. Passwords are read from the environment only — never printed,
# never written into the repo. Without those four, the AAB is unsigned and
# Play Console will not accept it until Grant signs it.
#
# Usage (from anywhere):
#   mobile/android/build-twa.sh
#
# Optional environment:
#   ANDROID_SDK_ROOT     SDK install root (default: $HOME/.android-sdk)
#   TWA_JDK_PATH         JDK 17 home (auto-detected when unset)
#   TWA_ARTIFACT_DIR     where to copy the AAB/APK (default: $PWD/artifacts/twa)
#   TWA_SKIP_TOOLCHAIN=1 skip JDK / SDK / bubblewrap installs (CI with preinstalled tools)
#   TWA_KEYSTORE_BASE64  upload keystore, base64 (CI secret; not a password)
#   TWA_KEYSTORE_PASSWORD / TWA_KEY_ALIAS / TWA_KEY_PASSWORD
#   TWA_SKIP_SIGNING=1   force unsigned even if signing secrets are present
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
# Bubblewrap 1.25's PlayBillingFeature pins this helper; its POM pulls
# com.android.billingclient:billing:8.3.0 (Play's v8+ new-app requirement).
BILLING_HELPER='com.google.androidbrowserhelper:billing:1.2.0'
BILLING_PERMISSION='com.android.vending.BILLING'

ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/.android-sdk}"
TWA_ARTIFACT_DIR="${TWA_ARTIFACT_DIR:-$REPO_ROOT/artifacts/twa}"
TWA_SKIP_TOOLCHAIN="${TWA_SKIP_TOOLCHAIN:-0}"
TWA_SKIP_SIGNING="${TWA_SKIP_SIGNING:-0}"
TWA_NPM_PREFIX="${TWA_NPM_PREFIX:-$HOME/.cache/badgeday-twa}"
BUBBLEWRAP=""
SIGNED_RELEASE=0
KEYSTORE_FILE=""

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
if billing.get("enabled") is not True:
    errors.append(f"features.playBilling.enabled is {billing.get('enabled')!r}, expected True")
alpha = manifest.get("alphaDependencies") or {}
if alpha.get("enabled") is not True:
    errors.append(f"alphaDependencies.enabled is {alpha.get('enabled')!r}, expected True")
if manifest.get("host") != "app.badgeday.com":
    errors.append(f"host is {manifest.get('host')!r}, expected 'app.badgeday.com'")
if errors:
    print("TWA guardrail failed:", file=sys.stderr)
    for item in errors:
        print(f"  - {item}", file=sys.stderr)
    sys.exit(1)
print(f"TWA guardrails ok: packageId={expected} playBilling=true host=app.badgeday.com")
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
    sdkmanager="$ANDROID_SDK_ROOT/bin/sdkmanager"
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

signing_secrets_present() {
  [ -n "${TWA_KEYSTORE_BASE64:-}" ] \
    && [ -n "${TWA_KEYSTORE_PASSWORD:-}" ] \
    && [ -n "${TWA_KEY_ALIAS:-}" ] \
    && [ -n "${TWA_KEY_PASSWORD:-}" ]
}

prepare_upload_keystore() {
  SIGNED_RELEASE=0
  KEYSTORE_FILE=""
  if [ "$TWA_SKIP_SIGNING" = 1 ]; then
    echo "Signing skipped (TWA_SKIP_SIGNING=1). The AAB will be unsigned."
    return
  fi
  if ! signing_secrets_present; then
    echo "No upload-keystore secrets in the environment. The AAB will be unsigned."
    echo "Grant: add TWA_KEYSTORE_BASE64 / TWA_KEYSTORE_PASSWORD / TWA_KEY_ALIAS / TWA_KEY_PASSWORD as CI secrets to produce a Play-uploadable signed AAB."
    return
  fi
  local dest="${TWA_KEYSTORE_FILE:-${RUNNER_TEMP:-/tmp}/badgeday-upload.keystore}"
  mkdir -p "$(dirname "$dest")"
  python3 - "$dest" <<'PY'
import base64, os, sys
path = sys.argv[1]
raw = os.environ["TWA_KEYSTORE_BASE64"].strip()
# Tolerate whitespace / newlines that GitHub secrets sometimes grow.
raw = "".join(raw.split())
data = base64.b64decode(raw)
if len(data) < 32:
    sys.exit("error: TWA_KEYSTORE_BASE64 did not decode to a keystore")
with open(path, "wb") as fh:
    fh.write(data)
os.chmod(path, 0o600)
PY
  KEYSTORE_FILE="$dest"
  SIGNED_RELEASE=1
  echo "Upload keystore written for this build only (not in the repo)."
}

# After bubblewrap update: require the Digital Goods / Play Billing wiring,
# and pin the helper version that carries Billing Library 8.3.0.
assert_generated_project() {
  local gradle="$ANDROID_DIR/app/build.gradle"
  local manifest="$ANDROID_DIR/app/src/main/AndroidManifest.xml"
  [ -f "$gradle" ] || {
    echo "error: generated $gradle missing" >&2
    exit 1
  }
  python3 - "$gradle" "$manifest" "$EXPECTED_PACKAGE" "$BILLING_HELPER" <<'PY'
import sys
gradle_path, manifest_path, expected, helper = sys.argv[1:5]
gradle = open(gradle_path, encoding="utf-8").read()
manifest = open(manifest_path, encoding="utf-8").read() if manifest_path else ""
errors = []
if f'applicationId "{expected}"' not in gradle and f"applicationId '{expected}'" not in gradle:
    errors.append(f"generated app/build.gradle does not set applicationId {expected}")
if helper not in gradle and "androidbrowserhelper:billing" not in gradle:
    errors.append("generated app/build.gradle is missing the Play Billing helper")
needles = ("PaymentActivity", "DigitalGoodsRequestHandler", "play.google.com/billing")
if manifest and not any(n in manifest for n in needles):
    errors.append("generated AndroidManifest.xml has no Play Billing / Digital Goods component")
if errors:
    print("Generated project guardrail failed:", file=sys.stderr)
    for item in errors:
        print(f"  - {item}", file=sys.stderr)
    sys.exit(1)
print("Generated project ok: applicationId set, Play Billing helper present")
PY
}

ensure_billing_permission() {
  local manifest="$ANDROID_DIR/app/src/main/AndroidManifest.xml"
  [ -f "$manifest" ] || {
    echo "error: generated $manifest missing" >&2
    exit 1
  }
  python3 - "$manifest" "$BILLING_PERMISSION" <<'PY'
from pathlib import Path
import sys
path, permission = Path(sys.argv[1]), sys.argv[2]
text = path.read_text(encoding="utf-8")
needle = f'android:name="{permission}"'
if needle in text:
    print(f"AndroidManifest already declares {permission}")
    raise SystemExit(0)
# Insert immediately after the root <manifest ...> tag so merge-order cannot
# drop it. The billingclient AAR also declares this; declaring it ourselves
# is what we can assert without unpacking the AAR.
insert = f'    <uses-permission android:name="{permission}" />\n'
idx = text.find(">")
if idx == -1:
    sys.exit("error: AndroidManifest.xml has no root tag")
# First '>' may be on <manifest ...>.
text = text[: idx + 1] + "\n" + insert + text[idx + 1 :]
path.write_text(text, encoding="utf-8")
print(f"Declared {permission} in AndroidManifest.xml")
PY
}

# Gradle reads the four signing env vars. Passwords stay in the process
# environment; they are not written to a properties file in the tree.
apply_release_signing() {
  [ "$SIGNED_RELEASE" = 1 ] || return 0
  local gradle="$ANDROID_DIR/app/build.gradle"
  python3 - "$gradle" "$KEYSTORE_FILE" <<'PY'
from pathlib import Path
import sys
path, keystore = Path(sys.argv[1]), sys.argv[2]
text = path.read_text(encoding="utf-8")
if "signingConfig signingConfigs.release" in text:
    print("Release signing config already present")
    raise SystemExit(0)
block = """
    signingConfigs {
        release {
            storeFile file(%r)
            storePassword System.getenv("TWA_KEYSTORE_PASSWORD")
            keyAlias System.getenv("TWA_KEY_ALIAS")
            keyPassword System.getenv("TWA_KEY_PASSWORD")
        }
    }
""" % keystore
# Place signingConfigs inside the android { } block, before buildTypes if we can.
marker = "    buildTypes {"
if marker in text:
    text = text.replace(marker, block + marker, 1)
else:
    text = text.replace("android {", "android {\n" + block, 1)
text = text.replace(
    "        release {\n",
    "        release {\n            signingConfig signingConfigs.release\n",
    1,
)
path.write_text(text, encoding="utf-8")
print("Release signing config applied from CI env (passwords not written to disk)")
PY
}

copy_artifacts() {
  mkdir -p "$TWA_ARTIFACT_DIR"
  local copied=0
  local src dest note
  local aab="$ANDROID_DIR/app/build/outputs/bundle/release/app-release.aab"
  local apk_unsigned="$ANDROID_DIR/app/build/outputs/apk/release/app-release-unsigned.apk"
  local apk_signed="$ANDROID_DIR/app/build/outputs/apk/release/app-release.apk"

  if [ -f "$aab" ]; then
    if [ "$SIGNED_RELEASE" = 1 ]; then
      dest="$TWA_ARTIFACT_DIR/badgeday-twa.aab"
    else
      dest="$TWA_ARTIFACT_DIR/badgeday-twa-unsigned.aab"
    fi
    cp -f "$aab" "$dest"
    echo "copied $aab -> $dest"
    copied=1
  fi

  # APK is optional; Play wants the AAB. Keep one around for sideload smoke tests.
  for src in "$apk_unsigned" "$apk_signed"; do
    [ -f "$src" ] || continue
    dest="$TWA_ARTIFACT_DIR/badgeday-twa-unsigned.apk"
    [ "$SIGNED_RELEASE" = 1 ] && dest="$TWA_ARTIFACT_DIR/badgeday-twa.apk"
    cp -f "$src" "$dest"
    echo "copied $src -> $dest"
    copied=1
    break
  done

  if [ "$copied" -eq 0 ]; then
    echo "error: build finished but no AAB/APK was found under $ANDROID_DIR" >&2
    exit 1
  fi

  # Confirm the packaged AAB still names the billing permission. The proto-xml
  # inside an AAB keeps the permission string in cleartext.
  if [ -f "$aab" ]; then
    python3 - "$aab" "$BILLING_PERMISSION" <<'PY'
import sys, zipfile
aab, permission = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(aab) as zf:
    names = zf.namelist()
    payload = b""
    for name in names:
        if name.endswith("AndroidManifest.xml"):
            payload += zf.read(name)
    if permission.encode() not in payload:
        sys.exit(f"error: {aab} AndroidManifest does not mention {permission}")
print(f"AAB declares {permission}")
PY
  fi

  note="$TWA_ARTIFACT_DIR/BUILD_NOTES.txt"
  {
    echo "packageId=$EXPECTED_PACKAGE"
    echo "host=app.badgeday.com"
    echo "playBilling=true"
    echo "signed=$SIGNED_RELEASE"
    echo "billingPermission=$BILLING_PERMISSION"
    echo "billingHelper=$BILLING_HELPER"
    if [ "$SIGNED_RELEASE" = 1 ]; then
      echo "playUpload=ready (signed with the CI upload keystore)"
    else
      echo "playUpload=blocked-until-signed"
      echo "Grant: create an upload keystore, add the four TWA_* CI secrets, re-run this workflow — or sign this AAB locally. Do not commit the keystore or its passwords."
    fi
  } > "$note"
}

bundle_release() {
  local wrapper="$ANDROID_DIR/gradlew"
  [ -x "$wrapper" ] || {
    echo "error: generated $wrapper missing; bubblewrap update did not produce a Gradle wrapper" >&2
    exit 1
  }
  (
    cd "$ANDROID_DIR"
    ./gradlew --no-daemon :app:bundleRelease
  )
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
  prepare_upload_keystore

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
  ensure_billing_permission
  apply_release_signing

  # Gradle bundle, not `bubblewrap build`: that command prompts for a keystore
  # password. Signing, when requested, is the env-driven gradle config above.
  bundle_release
  assert_twa_guardrails
  copy_artifacts
  echo "TWA compile finished. Artifacts in $TWA_ARTIFACT_DIR"
}

main "$@"
