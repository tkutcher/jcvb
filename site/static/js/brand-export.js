/* JCVB — brand asset exporter. Progressive enhancement only.
 *
 * Each tile already links its source PNG for a quick grab. This adds a
 * re-render path: pick a format, size, background and margin, and the artwork
 * is composited onto a canvas in the browser. It has to happen client-side —
 * the site is static files on blob storage, there is no server to resize
 * anything.
 *
 * Every logo PNG is transparent artwork, so painting a background actually
 * works instead of stacking one rectangle on another. The three colorways
 * ("on dark" / "on light" / "on gold") differ in *ink* color, not background,
 * so a tile's colorway stays fixed here and only the background is
 * selectable — pick the colorway that contrasts with the background you want.
 */
(function () {
  "use strict";

  var tiles = document.querySelectorAll("[data-export-src]");
  if (!tiles.length) return;

  // Everything below needs these three. Without them the direct PNG links on
  // each tile still work, so the right move is to add no buttons at all.
  var canProbe = document.createElement("canvas");
  if (
    !window.HTMLDialogElement ||
    typeof canProbe.toBlob !== "function" ||
    !canProbe.getContext
  ) {
    return;
  }

  var BACKGROUNDS = {
    transparent: null,
    black: "#0A0203", // --jc-black
    gold: "#C4B781", // --jc-gold
    cream: "#F5F1E6", // --jc-cream
    white: "#FFFFFF"
  };

  var FORMATS = {
    png: { mime: "image/png", ext: "png", alpha: true },
    jpeg: { mime: "image/jpeg", ext: "jpg", alpha: false },
    webp: { mime: "image/webp", ext: "webp", alpha: true }
  };

  var SIZES = [256, 512, 1024, 2048];

  /* ---- Dialog ---- */
  var dlg = document.createElement("dialog");
  dlg.className = "export-dlg";
  dlg.innerHTML =
    '<form method="dialog" class="export-dlg__close-form">' +
    '<button value="cancel" class="export-dlg__x" aria-label="Close">&times;</button>' +
    "</form>" +
    '<h3 class="export-dlg__title">Export <span data-x="label"></span></h3>' +
    '<div class="export-dlg__body">' +
    '  <div class="export-preview" data-x="stage"><canvas data-x="canvas"></canvas></div>' +
    '  <div class="export-controls">' +
    '    <label>Format' +
    '      <select data-x="format">' +
    '        <option value="png">PNG — transparency</option>' +
    '        <option value="jpeg">JPG — smaller, opaque</option>' +
    '        <option value="webp">WEBP — smallest</option>' +
    "      </select>" +
    "    </label>" +
    '    <label>Size <span class="export-hint" data-x="native"></span>' +
    '      <select data-x="size"></select>' +
    "    </label>" +
    '    <label data-x="customwrap" hidden>Custom size (px)' +
    '      <input type="number" data-x="custom" min="16" max="4096" step="1" value="1024">' +
    "    </label>" +
    "    <label>Shape" +
    '      <select data-x="shape">' +
    '        <option value="auto">Match artwork</option>' +
    '        <option value="square">Square — avatars, app icons</option>' +
    "      </select>" +
    "    </label>" +
    "    <label>Background" +
    '      <select data-x="bg">' +
    '        <option value="transparent">Transparent</option>' +
    '        <option value="black">JC Black</option>' +
    '        <option value="gold">JC Gold</option>' +
    '        <option value="cream">JC Cream</option>' +
    '        <option value="white">White</option>' +
    '        <option value="customcolor">Custom…</option>' +
    "      </select>" +
    "    </label>" +
    '    <label data-x="colorwrap" hidden>Custom color' +
    '      <input type="color" data-x="color" value="#C4B781">' +
    "    </label>" +
    '    <label>Margin <span class="export-hint" data-x="marginpx"></span>' +
    '      <input type="range" data-x="margin" min="0" max="25" step="1" value="0">' +
    "    </label>" +
    "  </div>" +
    "</div>" +
    '<p class="export-note" data-x="note"></p>' +
    '<div class="export-dlg__foot">' +
    '  <code class="export-filename" data-x="filename"></code>' +
    '  <button type="button" class="btn btn--gold" data-x="download">Download</button>' +
    "</div>";
  document.body.appendChild(dlg);

  function q(name) {
    return dlg.querySelector('[data-x="' + name + '"]');
  }
  var els = {
    label: q("label"),
    stage: q("stage"),
    canvas: q("canvas"),
    format: q("format"),
    size: q("size"),
    customwrap: q("customwrap"),
    custom: q("custom"),
    shape: q("shape"),
    bg: q("bg"),
    colorwrap: q("colorwrap"),
    color: q("color"),
    margin: q("margin"),
    marginpx: q("marginpx"),
    native: q("native"),
    note: q("note"),
    filename: q("filename"),
    download: q("download")
  };

  var current = { img: null, name: "", label: "" };

  /* ---- Compose ---- */

  // The canvas that backs the preview is the same one that gets exported, so
  // what you see is exactly what downloads. CSS scales it down for display.
  function compose() {
    var img = current.img;
    if (!img || !img.naturalWidth) return null;

    var fmt = FORMATS[els.format.value];
    var size =
      els.size.value === "custom"
        ? Math.min(4096, Math.max(16, parseInt(els.custom.value, 10) || 1024))
        : parseInt(els.size.value, 10);

    var nw = img.naturalWidth;
    var nh = img.naturalHeight;
    var cw;
    var ch;
    if (els.shape.value === "square") {
      cw = ch = size;
    } else if (nw >= nh) {
      cw = size;
      ch = Math.max(1, Math.round((size * nh) / nw));
    } else {
      ch = size;
      cw = Math.max(1, Math.round((size * nw) / nh));
    }

    // Margin reads off the short edge so a wide lockup doesn't lose its whole
    // height to padding. The px value is shown in the UI so there's no guessing.
    var pad = Math.round((Math.min(cw, ch) * parseInt(els.margin.value, 10)) / 100);
    var availW = Math.max(1, cw - pad * 2);
    var availH = Math.max(1, ch - pad * 2);
    var scale = Math.min(availW / nw, availH / nh);
    var dw = Math.max(1, Math.round(nw * scale));
    var dh = Math.max(1, Math.round(nh * scale));

    var bgKey = els.bg.value;
    var bg = bgKey === "customcolor" ? els.color.value : BACKGROUNDS[bgKey];
    // JPEG has no alpha. Rather than silently producing a black box, fall back
    // to white and say so in the note.
    var forcedBg = false;
    if (!fmt.alpha && !bg) {
      bg = "#FFFFFF";
      forcedBg = true;
    }

    var canvas = els.canvas;
    canvas.width = cw;
    canvas.height = ch;
    var ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, cw, ch);
    if (bg) {
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, cw, ch);
    }
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, Math.round((cw - dw) / 2), Math.round((ch - dh) / 2), dw, dh);

    els.stage.classList.toggle("is-transparent", !bg);
    return {
      fmt: fmt,
      w: cw,
      h: ch,
      pad: pad,
      bgKey: bg ? (bgKey === "customcolor" ? "custom" : bgKey) : "transparent",
      forcedBg: forcedBg,
      upscaled: size > Math.max(nw, nh)
    };
  }

  function filenameFor(out) {
    var parts = [current.name, out.w + "x" + out.h, out.bgKey];
    if (out.pad > 0) parts.push("m" + els.margin.value);
    return parts.join("-") + "." + out.fmt.ext;
  }

  function refresh() {
    els.customwrap.hidden = els.size.value !== "custom";
    els.colorwrap.hidden = els.bg.value !== "customcolor";

    var out = compose();
    if (!out) return;

    els.marginpx.textContent = out.pad > 0 ? out.pad + "px each side" : "none";
    els.filename.textContent = filenameFor(out);

    var notes = [];
    if (out.upscaled) {
      notes.push(
        "Larger than the source art (" +
          current.img.naturalWidth +
          "×" +
          current.img.naturalHeight +
          ") — it will look soft."
      );
    }
    if (out.forcedBg) notes.push("JPG can't hold transparency, so this exports on white.");
    els.note.textContent = notes.join(" ");
    els.note.hidden = notes.length === 0;
  }

  /* ---- Open / download ---- */

  function open(btn) {
    current.name = btn.getAttribute("data-export-name");
    current.label = btn.getAttribute("data-export-label") || current.name;
    els.label.textContent = current.label;

    // Drop the previous asset before loading the next one. Without this, a
    // failed load would leave the last tile's artwork on the canvas — and
    // downloadable under this tile's filename.
    current.img = null;
    els.canvas.width = els.canvas.height = 0;
    els.filename.textContent = "";
    els.note.hidden = true;

    var img = new Image();
    img.onerror = function () {
      els.note.textContent = "Could not load that asset. Use the PNG ↓ link instead.";
      els.note.hidden = false;
    };
    img.onload = function () {
      current.img = img;
      var long = Math.max(img.naturalWidth, img.naturalHeight);
      els.native.textContent = "source " + img.naturalWidth + "×" + img.naturalHeight;
      // Rebuild the size list per asset so the presets that upscale are
      // marked before you pick one, not after.
      els.size.innerHTML = "";
      SIZES.forEach(function (s) {
        var o = document.createElement("option");
        o.value = String(s);
        o.textContent = s + "px" + (s > long ? " (upscaled)" : "");
        els.size.appendChild(o);
      });
      var native = document.createElement("option");
      native.value = String(long);
      native.textContent = long + "px (native)";
      els.size.appendChild(native);
      var custom = document.createElement("option");
      custom.value = "custom";
      custom.textContent = "Custom…";
      els.size.appendChild(custom);
      els.size.value = String(long);
      refresh();
    };
    img.src = btn.getAttribute("data-export-src");

    dlg.showModal();
  }

  els.download.addEventListener("click", function () {
    var out = compose();
    if (!out) return;
    var name = filenameFor(out);
    els.canvas.toBlob(
      function (blob) {
        if (!blob) return;
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        // Revoking immediately can cancel the download in some browsers.
        setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
      },
      out.fmt.mime,
      0.92
    );
  });

  dlg.addEventListener("input", refresh);
  dlg.addEventListener("change", refresh);

  document.querySelectorAll("[data-export-src]").forEach(function (btn) {
    btn.hidden = false;
    btn.addEventListener("click", function () { open(btn); });
  });
})();
