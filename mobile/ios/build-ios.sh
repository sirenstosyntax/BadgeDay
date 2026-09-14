#!/usr/bin/env bash
# Generate the Capacitor iOS project, patch it, then compile, archive, or
# upload to TestFlight.
#
# The native Xcode tree is gitignored. This script is the durable path:
#   npm ci → npx cap add ios (if needed) → npx cap sync ios → patch → build.
#
# IAP product create stays HELD. This script never calls Fastlane produce /
# deliver IAP, never invents a product id, and never writes a signing secret
# into the repo.
#
# Usage (from anywhere, on macOS with Xcode):
#   mobile/ios/build-ios.sh compile
#   mobile/ios/build-ios.sh archive
#   mobile/ios/build-ios.sh upload
#
# Environment (names only — values are CI secrets):
#   APP_STORE_CONNECT_API_KEY_ID
#   APP_STORE_CONNECT_ISSUER_ID
#   APP_STORE_CONNECT_API_KEY_P8
#   IOS_DISTRIBUTION_CERTIFICATE_P12_BASE64   (durable signing)
#   IOS_DISTRIBUTION_CERTIFICATE_PASSWORD
#   IOS_PROVISIONING_PROFILE_BASE64           (optional; sigh can fetch)
#   IOS_ARTIFACT_DIR
#   IOS_MARKETING_VERSION
#   IOS_BUILD_NUMBER
#   IOS_SKIP_TOOLCHAIN=1
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IOS_DIR="$REPO_ROOT/mobile/ios"
PATCHER="$IOS_DIR/patch_native_ios.py"
EXPECTED_BUNDLE='com.badgeday.app'
TEAM_ID='G86W79K99V'

IOS_ARTIFACT_DIR="${IOS_ARTIFACT_DIR:-$REPO_ROOT/artifacts/ios}"
IOS_SKIP_TOOLCHAIN="${IOS_SKIP_TOOLCHAIN:-0}"
MODE="${1:-compile}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: required command not found: $1" >&2
    exit 1
  }
}

require_macos() {
  [ "$(uname -s)" = "Darwin" ] || {
    echo "error: iOS compile/archive needs macOS and Xcode. Use the TestFlight GitHub Actions workflow (macos-latest)." >&2
    exit 1
  }
}

api_key_secrets_present() {
  [ -n "${APP_STORE_CONNECT_API_KEY_ID:-}" ] \
    && [ -n "${APP_STORE_CONNECT_ISSUER_ID:-}" ] \
    && [ -n "${APP_STORE_CONNECT_API_KEY_P8:-}" ]
}

p12_secrets_present() {
  [ -n "${IOS_DISTRIBUTION_CERTIFICATE_P12_BASE64:-}" ] \
    && [ -n "${IOS_DISTRIBUTION_CERTIFICATE_PASSWORD:-}" ]
}

write_b64_file() {
  local dest="$1"
  local env_name="$2"
  python3 - "$dest" "$env_name" <<'PY'
import base64, os, sys
dest, name = sys.argv[1], sys.argv[2]
raw = os.environ[name].strip()
raw = "".join(raw.split())
data = base64.b64decode(raw)
if len(data) < 32:
    sys.exit(f"error: {name} did not decode to a usable file")
os.makedirs(os.path.dirname(dest), exist_ok=True)
with open(dest, "wb") as fh:
    fh.write(data)
os.chmod(dest, 0o600)
PY
}

write_p8_file() {
  local dest="$1"
  python3 - "$dest" <<'PY'
import base64, os, sys
dest = sys.argv[1]
raw = os.environ["APP_STORE_CONNECT_API_KEY_P8"].strip()
if "BEGIN" in raw:
    data = (raw if raw.endswith("\n") else raw + "\n").encode()
else:
    data = base64.b64decode("".join(raw.split()))
if b"BEGIN" not in data:
    sys.exit("error: APP_STORE_CONNECT_API_KEY_P8 is not a PEM key")
os.makedirs(os.path.dirname(dest), exist_ok=True)
with open(dest, "wb") as fh:
    fh.write(data)
os.chmod(dest, 0o600)
PY
}

assert_shell_guardrails() {
  python3 - "$IOS_DIR/capacitor.config.json" "$IOS_DIR/package.json" "$EXPECTED_BUNDLE" <<'PY'
import json, sys
config_path, pkg_path, expected = sys.argv[1], sys.argv[2], sys.argv[3]
config = json.loads(open(config_path, encoding="utf-8").read())
pkg = json.loads(open(pkg_path, encoding="utf-8").read())
errors = []
if config.get("appId") != expected:
    errors.append(f"appId is {config.get('appId')!r}, expected {expected!r}")
if (config.get("server") or {}).get("url") != "https://app.badgeday.com":
    errors.append("server.url must be https://app.badgeday.com")
deps = pkg.get("dependencies") or {}
if "@capgo/native-purchases" not in deps:
    errors.append("StoreKit plugin @capgo/native-purchases must stay declared")
if errors:
    print("iOS shell guardrail failed:", file=sys.stderr)
    for item in errors:
        print(f"  - {item}", file=sys.stderr)
    sys.exit(1)
print(f"iOS shell guardrails ok: appId={expected} host=app.badgeday.com")
PY
}

prepare_signing_files() {
  unset IOS_DISTRIBUTION_CERTIFICATE_P12_PATH IOS_PROVISIONING_PROFILE_PATH
  if ! api_key_secrets_present; then
    return 0
  fi
  local tmp="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
  tmp="${tmp%/}/badgeday-ios-signing"
  mkdir -p "$tmp"
  chmod 700 "$tmp"
  write_p8_file "$tmp/AuthKey.p8"
  export APP_STORE_CONNECT_API_KEY_PATH="$tmp/AuthKey.p8"
  if p12_secrets_present; then
    write_b64_file "$tmp/distribution.p12" IOS_DISTRIBUTION_CERTIFICATE_P12_BASE64
    export IOS_DISTRIBUTION_CERTIFICATE_P12_PATH="$tmp/distribution.p12"
  fi
  if [ -n "${IOS_PROVISIONING_PROFILE_BASE64:-}" ]; then
    write_b64_file "$tmp/BadgeDay_AppStore.mobileprovision" IOS_PROVISIONING_PROFILE_BASE64
    export IOS_PROVISIONING_PROFILE_PATH="$tmp/BadgeDay_AppStore.mobileprovision"
  fi
}

install_js_deps() {
  require_cmd npm
  require_cmd npx
  (
    cd "$IOS_DIR"
    if [ "$IOS_SKIP_TOOLCHAIN" = 1 ] && [ -d node_modules/@capacitor/cli ]; then
      echo "npm ci skipped (IOS_SKIP_TOOLCHAIN=1 and node_modules present)"
      return
    fi
    npm ci
  )
}

cap_add_failure_is_expected_pod_refusal() {
  # Only the Capacitor 14.0 template vs CapgoNativePurchases 15.0
  # CocoaPods refusal is expected. Presence of pbxproj is not enough.
  local log="$1"
  grep -qiE 'CapgoNativePurchases' "$log" \
    && grep -qiE 'higher minimum deployment target|deployment.target' "$log"
}

add_native_project() {
  (
    cd "$IOS_DIR"
    export LANG="${LANG:-en_US.UTF-8}"
    export LC_ALL="${LC_ALL:-en_US.UTF-8}"
    if [ -f ios/App/App.xcodeproj/project.pbxproj ]; then
      exit 0
    fi
    # A CocoaPods cache of ios/App/Pods (or any leftover generate-in-CI
    # tree) can create ./ios without a pbxproj. Capacitor then refuses
    # `cap add` with "ios platform already exists." That is not the
    # CapgoNativePurchases refusal and is not success.
    if [ -e ios ]; then
      echo "Removing stale ios/ (no project.pbxproj — leftover or partial CocoaPods cache)."
      rm -rf ios
    fi
    echo "Generating native iOS project (npx cap add ios --packagemanager Cocoapods)…"
    # Capacitor 7 defaults to CocoaPods; Capacitor 8 defaults to SPM.
    # Pin CocoaPods so a lockfile bump cannot silently change the project
    # shape under Fastlane. Third-party plugins here are pods-first.
    #
    # `cap add` copies the template (iOS 14.0) and then runs pod install.
    # @capgo/native-purchases requires 15.0, so that first pod install
    # fails with a deployment-target / CapgoNativePurchases refusal.
    # Only that refusal is treated as expected; any other failure is
    # fatal even if project.pbxproj already exists.
    cap_add_log="$(mktemp)"
    set +e
    npx cap add ios --packagemanager Cocoapods >"$cap_add_log" 2>&1
    cap_add_status=$?
    set -e
    cat "$cap_add_log"
    if [ "$cap_add_status" -eq 0 ]; then
      rm -f "$cap_add_log"
      exit 0
    fi
    if [ ! -f ios/App/App.xcodeproj/project.pbxproj ]; then
      echo "error: npx cap add ios failed before writing the Xcode project" >&2
      rm -f "$cap_add_log"
      exit 1
    fi
    if cap_add_failure_is_expected_pod_refusal "$cap_add_log"; then
      echo "cap add ios stopped at pod install (template is iOS 14.0 / CapgoNativePurchases refuses). Will raise the deployment target and sync."
      rm -f "$cap_add_log"
      exit 0
    fi
    echo "error: npx cap add ios failed for an unexpected reason (not the iOS 14.0 / CapgoNativePurchases deployment-target refusal). Not treating pbxproj presence as success." >&2
    rm -f "$cap_add_log"
    exit 1
  )
}

sync_native_project() {
  (
    cd "$IOS_DIR"
    export LANG="${LANG:-en_US.UTF-8}"
    export LC_ALL="${LC_ALL:-en_US.UTF-8}"
    echo "Syncing Capacitor iOS plugins…"
    npx cap sync ios
  )
}

patch_native_project() {
  local marketing="${IOS_MARKETING_VERSION:-}"
  local build="${IOS_BUILD_NUMBER:-${GITHUB_RUN_NUMBER:-1}}"
  local args=(apply "$IOS_DIR" --build-number "$build")
  if [ -n "$marketing" ]; then
    args+=(--marketing-version "$marketing")
  fi
  python3 "$PATCHER" "${args[@]}"
}

compile_simulator() {
  require_cmd xcodebuild
  local workspace="$IOS_DIR/ios/App/App.xcworkspace"
  local project="$IOS_DIR/ios/App/App.xcodeproj"
  local -a xcode_src
  if [ -f "$workspace/contents.xcworkspacedata" ]; then
    xcode_src=(-workspace "$workspace")
  else
    xcode_src=(-project "$project")
  fi
  echo "Compiling for iOS Simulator (unsigned; proves cap add + patch)…"
  (
    cd "$IOS_DIR"
    xcodebuild \
      "${xcode_src[@]}" \
      -scheme App \
      -configuration Debug \
      -destination 'generic/platform=iOS Simulator' \
      -sdk iphonesimulator \
      CODE_SIGNING_ALLOWED=NO \
      build
  )
}

run_fastlane() {
  local lane="$1"
  require_cmd bundle
  (
    cd "$IOS_DIR"
    if [ "$IOS_SKIP_TOOLCHAIN" != 1 ] && ! bundle check >/dev/null 2>&1; then
      bundle config set --local path vendor/bundle
      bundle install --jobs 4 --retry 3
    fi
    export FASTLANE_SKIP_UPDATE_CHECK=1
    export FASTLANE_HIDE_GITHUB_ISSUES=1
    bundle exec fastlane ios "$lane"
  )
}

write_notes() {
  local signed="$1"
  local upload_state="$2"
  mkdir -p "$IOS_ARTIFACT_DIR"
  local note="$IOS_ARTIFACT_DIR/BUILD_NOTES.txt"
  {
    echo "bundleId=$EXPECTED_BUNDLE"
    echo "teamId=$TEAM_ID"
    echo "host=app.badgeday.com"
    echo "nativeProject=generated-in-ci"
    echo "signed=$signed"
    echo "testflightUpload=$upload_state"
    echo "iapProductCreate=held"
    echo "mode=$MODE"
    if [ "$upload_state" = "blocked-until-secrets" ]; then
      echo "Grant: add APP_STORE_CONNECT_API_KEY_ID, APP_STORE_CONNECT_ISSUER_ID, APP_STORE_CONNECT_API_KEY_P8, IOS_DISTRIBUTION_CERTIFICATE_P12_BASE64, and IOS_DISTRIBUTION_CERTIFICATE_PASSWORD as GitHub Actions secrets, then re-run the TestFlight workflow (workflow_dispatch). Signed upload/archive fail closed until the P12 exists — CI will not mint a distribution cert whose private key dies with the runner. Do not create IAP products. Do not commit secrets."
    fi
  } > "$note"
  echo "Wrote $note"
}

main() {
  case "$MODE" in
    compile|archive|upload) ;;
    *)
      echo "usage: mobile/ios/build-ios.sh compile|archive|upload" >&2
      exit 2
      ;;
  esac

  [ -f "$IOS_DIR/capacitor.config.json" ] || {
    echo "error: missing $IOS_DIR/capacitor.config.json" >&2
    exit 1
  }
  require_macos
  require_cmd python3
  assert_shell_guardrails

  install_js_deps
  add_native_project
  patch_native_project
  sync_native_project
  patch_native_project
  if [ -f "$IOS_DIR/ios/App/Podfile" ]; then
    echo "Reconciling CocoaPods after the iOS 15.0 patch…"
    (cd "$IOS_DIR/ios/App" && pod install)
  fi
  python3 "$PATCHER" assert "$IOS_DIR" --build-number "${IOS_BUILD_NUMBER:-${GITHUB_RUN_NUMBER:-1}}" \
    ${IOS_MARKETING_VERSION:+--marketing-version "$IOS_MARKETING_VERSION"}

  mkdir -p "$IOS_ARTIFACT_DIR"
  export IOS_ARTIFACT_DIR

  if [ "$MODE" = "compile" ]; then
    compile_simulator
    write_notes 0 blocked-until-secrets
    echo "iOS simulator compile finished. TestFlight upload was not attempted."
    return 0
  fi

  if ! api_key_secrets_present; then
    if [ "$MODE" = "upload" ]; then
      write_notes 0 blocked-until-secrets
      echo "error: TestFlight upload requested but App Store Connect API key secrets are missing. Not faking a green upload." >&2
      echo "Grant: add APP_STORE_CONNECT_API_KEY_ID, APP_STORE_CONNECT_ISSUER_ID, APP_STORE_CONNECT_API_KEY_P8. See mobile/ios/TESTFLIGHT_CI.md." >&2
      exit 1
    fi
    echo "No App Store Connect API key secrets. Falling back to simulator compile."
    compile_simulator
    write_notes 0 blocked-until-secrets
    return 0
  fi

  prepare_signing_files
  if ! p12_secrets_present || [ ! -f "${IOS_DISTRIBUTION_CERTIFICATE_P12_PATH:-}" ]; then
    write_notes 0 blocked-until-secrets
    echo "error: signed archive/upload fail closed until IOS_DISTRIBUTION_CERTIFICATE_P12_BASE64 and IOS_DISTRIBUTION_CERTIFICATE_PASSWORD exist. Will not mint a distribution cert whose private key dies with the runner." >&2
    echo "Grant: add the two P12 secrets. See mobile/ios/TESTFLIGHT_CI.md." >&2
    exit 1
  fi
  if [ "$MODE" = "archive" ]; then
    run_fastlane archive
    write_notes 1 ready
    echo "IPA exported. TestFlight upload was not attempted (mode=archive)."
    return 0
  fi

  run_fastlane upload
  write_notes 1 uploaded
  echo "TestFlight upload requested. IAP product create remains HELD."
}

main "$@"
