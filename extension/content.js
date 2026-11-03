// Accountability Image Filter — content script.
//
// Runs entirely on-device. Loads the NSFWJS model (bundled TensorFlow.js),
// scans images and video frames as the page renders, and blurs anything
// classified explicit before — or as soon as — it is visible. This is a
// best-effort layer: it catches explicit images on pages that aren't blocked
// outright. It is not perfect (the model guesses, and some cross-origin
// images cannot be read for scanning).

(() => {
  "use strict";

  // Classes NSFWJS returns: Drawing, Hentai, Neutral, Porn, Sexy.
  const EXPLICIT = { Porn: 0.6, Hentai: 0.6, Sexy: 0.8 };
  const MIN_SIZE = 48; // ignore tiny icons/sprites
  const BLUR_CSS = "blur(40px)";
  const MARK = "__am_scanned";

  let modelPromise = null;
  function getModel() {
    if (!modelPromise) {
      // nsfwjs + tf are provided by the bundled lib scripts.
      modelPromise = nsfwjs.load(); // model weights fetched once, then cached
    }
    return modelPromise;
  }

  function isExplicit(predictions) {
    for (const p of predictions) {
      const t = EXPLICIT[p.className];
      if (t !== undefined && p.probability >= t) return p;
    }
    return null;
  }

  function blur(el, reason) {
    el.style.filter = BLUR_CSS;
    el.style.transition = "filter 0.1s";
    el.setAttribute("data-am-blurred", reason || "explicit");
  }

  async function scanImage(img) {
    if (img[MARK]) return;
    img[MARK] = true;
    const w = img.naturalWidth || img.width;
    const h = img.naturalHeight || img.height;
    if (w < MIN_SIZE || h < MIN_SIZE) return;
    try {
      const model = await getModel();
      const preds = await model.classify(img);
      const hit = isExplicit(preds);
      if (hit) blur(img, `${hit.className} ${hit.probability.toFixed(2)}`);
    } catch (e) {
      // Cross-origin images taint the canvas and cannot be read. We do not
      // blur those blindly (that would hide most of the web); they are left
      // to the site filter and the screenshot monitor.
    }
  }

  function scanImages(root) {
    const imgs = (root || document).querySelectorAll("img:not([" + MARK + "])");
    imgs.forEach((img) => {
      if (img.complete) scanImage(img);
      else img.addEventListener("load", () => scanImage(img), { once: true });
    });
  }

  // Video: sample frames periodically into a canvas and classify.
  function watchVideos() {
    document.querySelectorAll("video:not([" + MARK + "])").forEach((v) => {
      v[MARK] = true;
      const canvas = document.createElement("canvas");
      setInterval(async () => {
        if (v.paused || v.ended || v.videoWidth < MIN_SIZE) return;
        canvas.width = v.videoWidth;
        canvas.height = v.videoHeight;
        try {
          canvas.getContext("2d").drawImage(v, 0, 0, canvas.width, canvas.height);
          const model = await getModel();
          const preds = await model.classify(canvas);
          if (isExplicit(preds)) blur(v, "video");
          else if (v.getAttribute("data-am-blurred") === "video") {
            v.style.filter = ""; // unblur once a frame is clean
            v.removeAttribute("data-am-blurred");
          }
        } catch (e) {
          /* cross-origin video frame not readable */
        }
      }, 1500);
    });
  }

  function scanAll() {
    scanImages(document);
    watchVideos();
  }

  // Initial pass, then watch for content added later (infinite scroll, SPAs).
  scanAll();
  const obs = new MutationObserver((muts) => {
    for (const m of muts) {
      m.addedNodes.forEach((n) => {
        if (n.nodeType !== 1) return;
        if (n.tagName === "IMG") scanImage(n);
        else scanImages(n);
        if (n.tagName === "VIDEO" || n.querySelector) watchVideos();
      });
    }
  });
  obs.observe(document.documentElement, { childList: true, subtree: true });
})();
