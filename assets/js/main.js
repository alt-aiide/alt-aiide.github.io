(function () {
  "use strict";
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- typed tagline ---------- */
  var typed = document.querySelector(".typed");
  if (typed) {
    var lines = typed.getAttribute("data-typed").split("|");
    if (reduced) {
      typed.textContent = lines[0];
    } else {
      var li = 0, ci = 0, deleting = false;
      (function tick() {
        var line = lines[li];
        ci += deleting ? -1 : 1;
        typed.textContent = line.slice(0, ci) || " ";
        var delay = deleting ? 25 : 55;
        if (!deleting && ci === line.length) { deleting = true; delay = 2200; }
        else if (deleting && ci === 0) { deleting = false; li = (li + 1) % lines.length; delay = 400; }
        setTimeout(tick, delay);
      })();
    }
  }

  /* ---------- mini battleship ---------- */
  var grid = document.getElementById("battleship");
  if (grid) {
    var N = 8;
    var FLEET = [
      { name: "a Paradigm Shift", len: 4 },
      { name: "a State-of-the-Art Result", len: 3 },
      { name: "a Novel Contribution", len: 3 },
      { name: "a Statistically Significant p-value", len: 2 }
    ];
    var PRAISE = [
      "Direct hit! Reviewers are weeping.",
      "HIT! That's going in the abstract.",
      "Impact detected. Citation count rising.",
      "HIT! Someone call the journal editors."
    ];
    var MISSES = [
      "Miss. Reframed as a negative result.",
      "Splash. Will be reported as an ablation.",
      "Miss. Moved to future work.",
      "Nothing there. Still accepted."
    ];
    var shots = 0, hits = 0, total = 0, owner = {}, ships = [];
    var msg = document.getElementById("bs-msg");
    var elShots = document.getElementById("bs-shots");
    var elHits = document.getElementById("bs-hits");
    var elTotal = document.getElementById("bs-total");

    var setup = function () {
      grid.innerHTML = "";
      owner = {}; ships = []; shots = 0; hits = 0; total = 0;
      FLEET.forEach(function (spec, si) {
        for (var tries = 0; tries < 500; tries++) {
          var horiz = Math.random() < 0.5;
          var r = Math.floor(Math.random() * (horiz ? N : N - spec.len + 1));
          var c = Math.floor(Math.random() * (horiz ? N - spec.len + 1 : N));
          var cells = [];
          for (var k = 0; k < spec.len; k++) cells.push(horiz ? r * N + c + k : (r + k) * N + c);
          if (cells.every(function (x) { return owner[x] === undefined; })) {
            cells.forEach(function (x) { owner[x] = si; });
            ships.push({ name: spec.name, cells: cells, left: spec.len });
            total += spec.len;
            break;
          }
        }
      });
      for (var i = 0; i < N * N; i++) {
        var b = document.createElement("button");
        b.className = "bs-cell";
        b.type = "button";
        b.setAttribute("aria-label", "Row " + (Math.floor(i / N) + 1) + ", column " + (i % N + 1));
        b.dataset.i = i;
        grid.appendChild(b);
      }
      render("Click the grid. A fleet of groundbreaking contributions is hiding somewhere.");
    };

    var render = function (text) {
      elShots.textContent = shots; elHits.textContent = hits; elTotal.textContent = total;
      msg.innerHTML = text;
    };
    var pick = function (arr) { return arr[Math.floor(Math.random() * arr.length)]; };

    grid.addEventListener("click", function (e) {
      var b = e.target.closest(".bs-cell");
      if (!b || b.disabled) return;
      var i = +b.dataset.i;
      b.disabled = true;
      shots++;
      if (owner[i] === undefined) {
        b.classList.add("miss");
        render(pick(MISSES));
        return;
      }
      hits++;
      b.classList.add("hit");
      var ship = ships[owner[i]];
      ship.left--;
      if (ship.left === 0) {
        ship.cells.forEach(function (x) { grid.children[x].classList.add("sunk"); });
        render("You sank <b>" + ship.name + "</b>! Submitting to ALT-AIIDE immediately.");
      } else {
        render(pick(PRAISE));
      }
      if (hits === total) {
        grid.querySelectorAll(".bs-cell:not(:disabled)").forEach(function (c) { c.disabled = true; });
        var verdict = shots <= 30 ? "Better than a deep Q-network." : shots <= 45 ? "On par with a tabular Q-learner." : "Below random. Publishing anyway.";
        render("Fleet cleared in <b>" + shots + "</b> shots. " + verdict + " <a href=\"#\" id=\"bs-again\">Play again?</a>");
        document.getElementById("bs-again").addEventListener("click", function (ev) { ev.preventDefault(); setup(); });
      }
    });
    setup();
  }

  /* ---------- novelty meter ---------- */
  var meter = document.querySelector(".meter");
  var fill = document.getElementById("meter-fill");
  var val = document.getElementById("meter-val");
  var startMeter = function () {
    fill.style.width = "100%";
    var t0 = performance.now();
    (function step(t) {
      var p = Math.min(1, (t - t0) / 3000);
      var eased = 1 - Math.pow(1 - p, 3);
      val.textContent = Math.round(eased * 100) + "%";
      if (p < 1) return requestAnimationFrame(step);
      var extra = 100;
      (function overflow() {
        extra = Math.floor(extra * 1.37 + 7);
        val.textContent = extra > 1e6 ? "ERROR: TOO NOVEL" : extra.toLocaleString() + "%";
        meter.classList.add("overflow");
        if (extra <= 1e6) setTimeout(overflow, 120);
      })();
    })(t0);
  };

  /* ---------- reveal on scroll ---------- */
  var papers = document.querySelectorAll(".paper");
  if (!("IntersectionObserver" in window) || reduced) {
    papers.forEach(function (p) { p.classList.add("in"); });
    if (meter) { fill.style.transition = "none"; fill.style.width = "100%"; val.textContent = "ERROR: TOO NOVEL"; }
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        if (en.target === meter) startMeter();
        else en.target.classList.add("in");
        io.unobserve(en.target);
      });
    }, { threshold: 0.15 });
    papers.forEach(function (p) { io.observe(p); });
    if (meter) io.observe(meter);
  }
})();
