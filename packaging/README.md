# Packaging & releases

How the "download one file and run it" apps are built.

## The idea

- [`../accountability_monitor/app.py`](../accountability_monitor/app.py) is the
  entry point. Double-clicked, it creates the config, registers the background
  agent to start at login, and opens the settings page — no Terminal.
- [`accountability-monitor.spec`](accountability-monitor.spec) tells
  **PyInstaller** how to bundle that (and Python itself, and the ML model
  libraries) into one self-contained executable.
- [`../.github/workflows/release.yml`](../.github/workflows/release.yml) runs
  PyInstaller on macOS, Windows, and Linux build machines and attaches the
  three downloads to a GitHub Release.

## Cutting a release

1. On GitHub, go to **Releases → Draft a new release**, create a tag like
   `v0.1.0`, and publish it.
2. The workflow runs automatically and attaches
   `accountability-monitor-macos.zip`, `-windows.zip`, and `-linux.zip`.
3. Point the website's Download button at the latest release.

(You can also trigger it manually from the **Actions** tab via "Run workflow".)

## Code signing (removes the scary warnings)

Unsigned apps trigger "unidentified developer" (macOS Gatekeeper) and
SmartScreen (Windows) warnings. Users can still open them (right-click → Open
on Mac; "More info → Run anyway" on Windows), which is fine for a free tool,
but signing removes the friction:

- **macOS:** an Apple Developer account ($99/yr) gives a Developer ID to sign
  and notarize. Add the identity/secrets in CI and set `codesign_identity` in
  the spec.
- **Windows:** a code-signing certificate from a CA, applied with `signtool`.

Signing is optional and can be added later without changing how the app works.

## First real test

This pipeline can't be verified until a release actually runs on GitHub's
machines. The first release is the real test: cut `v0.1.0`, download the Mac
build on an actual Mac, and confirm it opens the settings page and starts
monitoring. Expect to iterate once on the spec (PyInstaller sometimes needs a
missing module added to `hiddenimports`).
