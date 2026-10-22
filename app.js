/* Claquete: ligação em tempo real (WebSocket), chat, notificações. Sem dependências. */
(function () {
  var S = document.querySelector("script[data-uid]"); if (!S) return;
  var UID = +S.dataset.uid, I = document.getElementById("i18n"), L = I ? I.dataset : {}, base = document.title.replace(/^\(\d+\)\s*/, "");
  var ws = null, up = false, wait = 1000, H = {}, tmr = {};
  function on(e, f) { (H[e] = H[e] || []).push(f); }
  function emit(e, d) { (H[e] || []).forEach(function (f) { f(d); }); }
  function deb(k, f, ms) { clearTimeout(tmr[k]); tmr[k] = setTimeout(f, ms || 250); }
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function post(url, body) { return fetch(url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: body || "x=1" }); }

  function connect() {
    try { ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws"); } catch (x) { return; }
    ws.onopen = function () { up = true; wait = 1000; emit("open"); state(); };
    ws.onmessage = function (m) { try { var d = JSON.parse(m.data); emit(d.e, d); } catch (x) {} };
    ws.onclose = function () { up = false; ws = null; emit("close"); setTimeout(connect, wait); wait = Math.min(wait * 2, 30000); };
    ws.onerror = function () {};
  }
  connect();
  window.CLQ = { on: on, up: function () { return up; }, send: function (o) { if (up) ws.send(JSON.stringify(o)); } };

  /* ---------- contadores */
  function setb(k, n) { $$('[data-k="' + k + '"]').forEach(function (b) { b.textContent = n; b.hidden = !n; }); }
  function state() {
    fetch("/chat/state", { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (j) {
      setb("chat", j.chat); setb("notif", j.notif);
      document.title = (j.chat + j.notif ? "(" + (j.chat + j.notif) + ") " : "") + base;
    }).catch(function () {});
  }
  setInterval(function () { if (!up) state(); }, 20000);

  /* ---------- avisos */
  function toast(t, href) {
    var d = document.createElement("a"); d.className = "toast"; d.href = href || "#"; d.textContent = t; document.body.appendChild(d);
    setTimeout(function () { d.classList.add("go"); setTimeout(function () { d.remove(); }, 400); }, 6000);
  }
  function native(t, b) {
    try { if (window.Notification && Notification.permission === "granted" && document.hidden) new Notification(t, { body: b || "" }); } catch (x) {}
  }
  on("notif", function () {
    state();
    fetch("/notifications/latest", { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (j) {
      if (j && j.t) { toast("\u{1F514} " + j.t, "/notifications"); native(j.t, j.b); }
    }).catch(function () {});
  });
  var bn = $("#bn");
  if (bn) {
    if (!window.Notification || Notification.permission !== "default") bn.hidden = true;
    bn.onclick = function () { Notification.requestPermission().then(function () { bn.hidden = true; }); };
  }

  /* ---------- presença */
  function fmtSeen(ls) {
    if (!ls) return "";
    var d = new Date(), p = function (n) { return (n < 10 ? "0" : "") + n; }, td = d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
    return L.seen + " " + (ls.slice(0, 10) === td ? ls.slice(11, 16) : ls.slice(8, 10) + "/" + ls.slice(5, 7));
  }
  on("presence", function (d) {
    $$('[data-pres="' + d.u + '"]').forEach(function (x) { x.hidden = !d.on; });
    $$('[data-ps="' + d.u + '"]').forEach(function (x) { x.textContent = d.on ? L.online : fmtSeen(d.ls); x.dataset.base = x.textContent; });
  });

  /* ---------- lista do chat */
  var cl = $("#cl");
  function panels() {
    if (!cl) return;
    var cur = $("#msgs") ? $("#msgs").dataset.cid : 0;
    fetch("/chat/panels?cid=" + cur, { credentials: "same-origin" }).then(function (r) { return r.text(); }).then(function (t) {
      var w = document.createElement("div"); w.innerHTML = t;
      $$("[data-p]", w).forEach(function (p) { var d = $("#p-" + p.dataset.p); if (d) d.innerHTML = p.innerHTML; });
      var a = $("[data-bc]", w); if (a) { $$("#tb [data-t=c] .nb").forEach(function (b) { b.textContent = a.dataset.bc; b.hidden = !+a.dataset.bc; }); $$("#tb [data-t=f] .nb").forEach(function (b) { b.textContent = a.dataset.bf; b.hidden = !+a.dataset.bf; }); }
      filter();
    }).catch(function () {});
  }
  function filter() {
    var q = ($("#cq") ? $("#cq").value : "").toLowerCase();
    $$("#cl .ci").forEach(function (c) { c.hidden = q && (c.dataset.q || "").indexOf(q) < 0; });
  }
  if (cl) {
    $$("#tb button").forEach(function (b) {
      b.onclick = function () {
        $$("#tb button").forEach(function (x) { x.classList.toggle("on", x === b); });
        $$("#cl .pn").forEach(function (p) { p.hidden = p.id !== "p-" + b.dataset.t; });
      };
    });
    var q = $("#cq"); if (q) q.oninput = filter;
    var t0 = $("#tb [data-t=" + (cl.dataset.tab || "c") + "]"); if (t0) t0.onclick();
  }
  on("sync", function () { panels(); state(); });

  /* ---------- sala */
  var M = $("#msgs");
  if (M) {
    var CID = +M.dataset.cid, DM = M.dataset.dm === "1", last = +M.dataset.last, first = +M.dataset.first, lastDay = M.dataset.day || "", busy = 0, rs = $("#rs"), typT = null;
    var F = $("#sf"), IN = F ? F.elements.body : null;
    function dayLabel(d) {
      var n = new Date(), p = function (x) { return (x < 10 ? "0" : "") + x; }, f = function (o) { return o.getFullYear() + "-" + p(o.getMonth() + 1) + "-" + p(o.getDate()); };
      var y = new Date(n.getTime() - 864e5); return d === f(n) ? L.today : d === f(y) ? L.yest : d.slice(8, 10) + "/" + d.slice(5, 7) + "/" + d.slice(0, 4);
    }
    function mk(x) {
      var f = document.createDocumentFragment(), day = x.t.slice(0, 10);
      if (day !== lastDay && !x.before) { var s = document.createElement("div"); s.className = "ds"; s.textContent = dayLabel(day); f.appendChild(s); lastDay = day; }
      var d = document.createElement("div"); d.className = "mg" + (x.me ? " a" : ""); d.dataset.id = x.id; d.dataset.day = day;
      if (!x.me && !DM) { var w = document.createElement("small"); w.className = "who"; w.textContent = x.n; d.appendChild(w); }
      d.appendChild(document.createTextNode(x.b));
      var t = document.createElement("span"); t.className = "tm"; t.textContent = x.t.slice(11, 16); d.appendChild(t);
      if (x.me && DM) { var k = document.createElement("i"); k.className = "tk"; k.textContent = "✓"; t.appendChild(k); }
      f.appendChild(d); return f;
    }
    function bottom() { M.scrollTop = M.scrollHeight; }
    function add(x) { if (x.id <= last) return; var at = M.scrollHeight - M.scrollTop - M.clientHeight < 120 || x.me; M.appendChild(mk(x)); last = x.id; if (at) bottom(); }
    function markRead() { deb("rd", function () { post("/chat/" + CID + "/read"); state(); }, 300); }
    function poll() {
      if (busy) return; busy = 1;
      fetch("/chat/" + CID + "/poll?after=" + last, { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (j) { j.m.forEach(add); if (j.m.length) { panels(); state(); } busy = 0; }).catch(function () { busy = 0; });
    }
    setInterval(function () { if (!up) poll(); }, 4000);
    on("msg", function (d) {
      if (d.c === CID) {
        add({ id: d.id, me: d.u === UID, n: d.n, b: d.b, t: d.t });
        if (d.u !== UID) { if (document.visibilityState === "visible") markRead(); else native(d.n, d.b); }
      } else if (d.u !== UID) { native(d.n, d.b); }
      panels(); state();
    });
    on("read", function (d) {
      if (d.c !== CID || d.u === UID || !DM) return;
      $$(".mg.a", M).forEach(function (m) { if (+m.dataset.id <= d.upto) { var k = $(".tk", m); if (k) { k.textContent = "✓✓"; k.classList.add("rd"); } } });
    });
    on("typing", function (d) {
      if (d.c !== CID || !rs) return;
      if (rs.dataset.base === undefined || rs.dataset.base === "") rs.dataset.base = rs.textContent;
      rs.textContent = (DM ? "" : d.n + " ") + L.typing; rs.classList.add("ty");
      clearTimeout(typT); typT = setTimeout(function () { rs.classList.remove("ty"); rs.textContent = rs.dataset.base || ""; }, 3000);
    });
    on("open", poll);
    document.addEventListener("visibilitychange", function () { if (document.visibilityState === "visible") { markRead(); poll(); } });
    if (F) {
      F.onsubmit = function (ev) {
        ev.preventDefault(); var b = IN.value.trim(); if (!b) return; IN.value = "";
        post(F.action, "ajax=1&body=" + encodeURIComponent(b)).then(function () { if (!up) { busy = 0; poll(); } });
      };
      var lt = 0;
      IN.oninput = function () { var n = Date.now(); if (n - lt > 2000) { lt = n; CLQ.send({ t: "typing", c: CID }); } };
      if (matchMedia("(min-width:821px)").matches) IN.focus();
    }
    var mo = $("#more");
    if (mo) mo.onclick = function () {
      fetch("/chat/" + CID + "/poll?before=" + first, { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (j) {
        var h = M.scrollHeight, top = mo.nextSibling;
        j.m.forEach(function (x) { x.before = 1; M.insertBefore(mk(x), top); if (x.id < first) first = x.id; });
        M.scrollTop = M.scrollHeight - h; if (!j.more) mo.remove();
      });
    };
    bottom(); markRead();
  }

  /* ---------- foto de perfil: reduz no browser e envia em base64 */
  var AF = $("#avf");
  if (AF) {
    var fi = $("#avfile"), hid = $("#avdata"), pv = $("#avpv");
    fi.onchange = function () {
      var f = fi.files[0]; if (!f) return;
      var r = new FileReader();
      r.onload = function () {
        var im = new Image();
        im.onload = function () {
          var s = Math.min(im.width, im.height), c = document.createElement("canvas"); c.width = c.height = 256;
          c.getContext("2d").drawImage(im, (im.width - s) / 2, (im.height - s) / 2, s, s, 0, 0, 256, 256);
          var q = .86, d = c.toDataURL("image/jpeg", q); while (d.length > 90000 && q > .4) { q -= .1; d = c.toDataURL("image/jpeg", q); }
          hid.value = d; pv.src = d; pv.hidden = false; $("#avsave").hidden = false;
        };
        im.src = r.result;
      };
      r.readAsDataURL(f);
    };
  }
})();
