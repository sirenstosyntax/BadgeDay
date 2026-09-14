// Import a distribution P12 into a file keychain without putting the
// wrapping password on argv.
//
// Apple security(1) `import` has no stdin / fd / env passphrase form.
// The only non-GUI option is `-P passphrase` (visible in the process list).
// This helper calls SecPKCS12Import with kSecImportExportPassphrase instead.
//
// Usage: swift import_p12.swift P12_PATH KEYCHAIN_PATH
// Password: entire stdin (not argv, not the child environment).
//
// Exit 0: imported or already present.
// Exit 1: fail closed (MAC verification / import error).
// Exit 2: usage.
//
// Does not invent secrets. Never prints the password.
// IAP product create stays HELD.

import Foundation
import Security

guard CommandLine.arguments.count == 3 else {
    fputs("usage: import_p12.swift P12_PATH KEYCHAIN_PATH\n", stderr)
    exit(2)
}

let p12Path = CommandLine.arguments[1]
let keychainPath = CommandLine.arguments[2]

var password = String(data: FileHandle.standardInput.readDataToEndOfFile(), encoding: .utf8) ?? ""
if password.hasSuffix("\n") { password.removeLast() }
if password.hasSuffix("\r") { password.removeLast() }
guard !password.isEmpty else {
    fputs("error: P12 password on stdin is empty\n", stderr)
    exit(1)
}

guard let p12Data = try? Data(contentsOf: URL(fileURLWithPath: p12Path)), p12Data.count >= 32 else {
    fputs("error: P12 not found or too small at \(p12Path)\n", stderr)
    exit(1)
}

func openKeychain(_ path: String) -> (SecKeychain?, OSStatus) {
    var keychain: SecKeychain?
    if path.isEmpty || path == "login" {
        let status = SecKeychainCopyDefault(&keychain)
        return (keychain, status)
    }
    let status = SecKeychainOpen(path, &keychain)
    return (keychain, status)
}

let (keychain, openStatus) = openKeychain(keychainPath)
guard openStatus == errSecSuccess, let keychain else {
    fputs(
        "SecKeychainItemImport failed — cannot open keychain \(keychainPath) (OSStatus \(openStatus))\n",
        stderr
    )
    exit(1)
}

func trustedAccess() -> SecAccess? {
    let paths = ["/usr/bin/codesign", "/usr/bin/security", "/usr/bin/productbuild"]
    var apps: [SecTrustedApplication] = []
    for path in paths {
        var app: SecTrustedApplication?
        if SecTrustedApplicationCreateFromPath(path, &app) == errSecSuccess, let app {
            apps.append(app)
        }
    }
    var access: SecAccess?
    let status = SecAccessCreate(
        "BadgeDay distribution" as CFString,
        apps.isEmpty ? nil : (apps as CFArray),
        &access
    )
    return status == errSecSuccess ? access : nil
}

var options: [CFString: Any] = [
    kSecImportExportPassphrase: password,
    kSecImportExportKeychain: keychain,
]
if let access = trustedAccess() {
    options[kSecImportExportAccess] = access
}

var items: CFArray?
let status = SecPKCS12Import(p12Data as CFData, options as CFDictionary, &items)

if status == errSecSuccess || status == errSecDuplicateItem {
    exit(0)
}

let message = SecCopyErrorMessageString(status, nil) as String? ?? "OSStatus \(status)"
fputs("\(message) (OSStatus \(status))\n", stderr)
exit(1)
