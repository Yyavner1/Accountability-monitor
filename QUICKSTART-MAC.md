# Quickstart: run it on your Mac

This gets the whole loop working on your own Mac so you can see it in action.
About 10 minutes.

## 1. Get the code

```bash
git clone https://github.com/yyavner1/accountability-monitor
cd accountability-monitor
```

## 2. Create a Gmail App Password

The agent emails your partner through your Gmail. A normal password won't
work; you need an "App Password":

1. Turn on 2-Step Verification: https://myaccount.google.com/security
2. Create an App Password: https://myaccount.google.com/apppasswords
   (pick "Mail"). You'll get a 16-character code.

## 3. Install the agent

```bash
./install.sh
```

Then edit the config it created:

```bash
open -e "$HOME/Library/Application Support/AccountabilityMonitor/config.json"
```

Set these three:

- `"partner_email"` — where alerts go (use a second email of yours to test)
- `"sender_email"` — your Gmail address
- `"smtp_password"` — the 16-character App Password from step 2

## 4. Grant Screen Recording permission

System Settings → Privacy & Security → Screen Recording → add the Python at:

```
~/Library/Application Support/AccountabilityMonitor/venv/bin/python3
```

(Without this, captures are black. This is the fiddly Mac step.)

Then restart the agent:

```bash
launchctl unload ~/Library/LaunchAgents/com.accountability.monitor.plist
launchctl load   ~/Library/LaunchAgents/com.accountability.monitor.plist
```

## 5. Test it end to end

Run one capture-and-check cycle by hand and watch what happens:

```bash
"$HOME/Library/Application Support/AccountabilityMonitor/venv/bin/python3" \
  -m accountability_monitor.monitor \
  --config "$HOME/Library/Application Support/AccountabilityMonitor/config.json" \
  --once --verbose
```

Open an image the detector should flag before running it, and check whether
the partner email arrives.

## 6. (Optional) Turn on the website filter

```bash
sudo ./install_filter.sh
```

## 7. (Optional) Browser extension

```bash
cd extension && ./fetch-libs.sh
```

Then load the `extension` folder in `chrome://extensions` (Developer mode on).

---

When you hit a snag, copy me the output and I'll sort it. The most common
issue is step 4 (the permission), which makes captures come out blank.
