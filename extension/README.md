# Accountability Image Filter (browser extension)

A Chrome/Edge extension (Manifest V3) that blurs explicit images and video
frames on web pages, classified **on-device** with NSFWJS. It's the
in-browser layer: it catches explicit content on pages the website filter
doesn't block outright (social media, image search, etc.).

## Install

```bash
cd extension
./fetch-libs.sh        # downloads TensorFlow.js + NSFWJS into lib/
```

Then in Chrome or Edge:

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and choose this `extension` folder.

It runs on every page automatically.

## How it works

- `content.js` runs on each page, loads the NSFWJS model once, and classifies
  every image (and periodically each playing video's current frame).
- Anything scored explicit (`Porn`, `Hentai`, or high `Sexy`) is blurred.
- New content from infinite scroll or single-page apps is caught by a
  `MutationObserver`.

## Honest limitations

- **Cross-origin images can't always be scanned.** Browser security taints
  the canvas for images served from other domains without CORS headers, so
  the model can't read their pixels. Those are left to the website filter and
  the screenshot monitor rather than blurred blindly (which would hide most
  of the web).
- **The model guesses.** It misses some explicit images and over-blurs some
  innocent ones. Tune the thresholds at the top of `content.js`.
- **It's per-browser and removable.** It only protects the browser it's
  installed in, and the user can disable it in `chrome://extensions`. The
  screenshot monitor remains the accountability backstop for that.
- Firefox uses a slightly different extension format; this targets
  Chromium-based browsers (Chrome, Edge, Brave, Arc).

## Why the libraries aren't included

Manifest V3 forbids extensions from loading code from the internet at
runtime, so TensorFlow.js and NSFWJS must be bundled locally. `fetch-libs.sh`
downloads pinned versions into `lib/` (git-ignored). The model weights
themselves are fetched once on first use and cached by the browser.
