"""System-wide website filter via the hosts file (cross-platform).

The filter writes a managed block of `0.0.0.0 domain` lines into the system
hosts file, between two marker comments, so known adult domains resolve to
nowhere and never load in any browser or app. Applying or removing the block
requires administrator rights (the installer does this with sudo / elevation).

The agent itself runs as a normal user and cannot edit the hosts file; its
job here is to *watch* the block and raise an alert if it is removed or
emptied, which is the tamper signal. Self-healing (re-applying the block)
requires a root helper and is left to the installer / a privileged service.

The hosts file is a simple, free, self-hosted filter. It is not bulletproof:
an administrator can edit it back, and browsers using DNS-over-HTTPS may
bypass it. That is exactly why tampering is reported to the partner.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("monitor.blocker")

BLOCK_START = "# >>> accountability-monitor blocklist >>>"
BLOCK_END = "# <<< accountability-monitor blocklist <<<"


def hosts_path() -> Path:
    if sys.platform.startswith("win"):
        root = Path(r"C:\Windows\System32\drivers\etc\hosts")
        return root
    return Path("/etc/hosts")


def load_blocklist(path: Path) -> list[str]:
    """Read a blocklist file: one domain per line, '#' comments allowed.

    Lines may be bare domains or hosts-file style ('0.0.0.0 domain'); only the
    domain is kept. Duplicates and subdomain 'www.' variants are normalized.
    """
    domains: set[str] = set()
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        domain = parts[-1].strip().lower()
        if "." not in domain:
            continue
        domains.add(domain)
    return sorted(domains)


def compile_block(domains: list[str]) -> str:
    lines = [BLOCK_START]
    for d in domains:
        lines.append(f"0.0.0.0 {d}")
        lines.append(f"0.0.0.0 www.{d}")
    lines.append(BLOCK_END)
    return "\n".join(lines) + "\n"


def _strip_existing(text: str) -> str:
    if BLOCK_START not in text:
        return text
    before, _, rest = text.partition(BLOCK_START)
    _, _, after = rest.partition(BLOCK_END)
    return before.rstrip("\n") + "\n" + after.lstrip("\n")


def apply_block(domains: list[str], hosts: Path | None = None) -> None:
    """Write/replace the managed block in the hosts file. Needs admin rights."""
    hosts = hosts or hosts_path()
    current = hosts.read_text() if hosts.exists() else ""
    cleaned = _strip_existing(current).rstrip("\n") + "\n\n"
    hosts.write_text(cleaned + compile_block(domains))
    log.info("applied blocklist (%d domains) to %s", len(domains), hosts)


def remove_block(hosts: Path | None = None) -> None:
    hosts = hosts or hosts_path()
    if not hosts.exists():
        return
    hosts.write_text(_strip_existing(hosts.read_text()))
    log.info("removed blocklist from %s", hosts)


def block_is_intact(hosts: Path | None = None, min_entries: int = 1) -> bool:
    """True if the managed block is present and has at least min_entries hosts."""
    hosts = hosts or hosts_path()
    try:
        text = hosts.read_text()
    except Exception as exc:  # pragma: no cover - runtime safety
        log.warning("could not read hosts file (%s)", exc)
        return True  # don't false-alarm if we simply can't read it
    if BLOCK_START not in text or BLOCK_END not in text:
        return False
    section = text.partition(BLOCK_START)[2].partition(BLOCK_END)[0]
    entries = [ln for ln in section.splitlines() if ln.strip().startswith("0.0.0.0")]
    return len(entries) >= min_entries


def main(argv: list[str] | None = None) -> int:
    """CLI to apply/remove/check the filter. Apply/remove need admin rights."""
    import argparse

    parser = argparse.ArgumentParser(description="Website filter (hosts file)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_apply = sub.add_parser("apply", help="write the blocklist into the hosts file")
    p_apply.add_argument("blocklist", help="path to a blocklist.txt")
    sub.add_parser("remove", help="remove the managed block")
    sub.add_parser("status", help="report whether the block is intact")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.cmd == "apply":
            apply_block(load_blocklist(Path(args.blocklist)))
        elif args.cmd == "remove":
            remove_block()
        elif args.cmd == "status":
            print("intact" if block_is_intact() else "MISSING/TAMPERED")
    except PermissionError:
        print(
            "Permission denied editing the hosts file. Re-run with "
            "administrator rights (sudo on macOS/Linux, elevated PowerShell "
            "on Windows).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
