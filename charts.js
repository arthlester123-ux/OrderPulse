/* OrderPulse front-end: Chart.js charts, table views, theme toggle, filter presets, SQL highlighting. */
(function () {
    "use strict";
    var charts = {};      // canvas id -> Chart instance
    var extras = {};      // canvas id -> extra table column {name, values}

    function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
    function fmtInt(v) { return Math.round(v).toLocaleString("en-US"); }
    function peso(v) { return "₱" + Math.round(v).toLocaleString("en-US"); }
    function compact(v) {
        var a = Math.abs(v);
        if (a >= 1e6) return "₱" + (v / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
        if (a >= 1e3) return "₱" + Math.round(v / 1e3) + "K";
        return "₱" + Math.round(v);
    }

    /* ---------- shared plugins ---------- */
    // Value label at the end of each bar (selective direct labelling for ranked bars)
    var barEndLabels = {
        id: "barEndLabels",
        afterDatasetsDraw: function (chart, _a, opts) {
            if (!opts || !opts.format) return;
            var ctx = chart.ctx, horiz = chart.options.indexAxis === "y";
            var meta = chart.getDatasetMeta(0);
            ctx.save();
            ctx.font = "600 11px 'Segoe UI', system-ui, sans-serif";
            ctx.fillStyle = css("--text-2");
            ctx.textBaseline = "middle";
            meta.data.forEach(function (bar, i) {
                var v = chart.data.datasets[0].data[i];
                var txt = opts.format(v, i);
                if (horiz) { ctx.textAlign = "left"; ctx.fillText(txt, bar.x + 6, bar.y); }
                else { ctx.textAlign = "center"; ctx.textBaseline = "bottom"; ctx.fillText(txt, bar.x, bar.y - 4); }
            });
            ctx.restore();
        }
    };
    // Total in the middle of a doughnut
    var centerText = {
        id: "centerText",
        afterDraw: function (chart, _a, opts) {
            if (!opts || !opts.text) return;
            var a = chart.chartArea, ctx = chart.ctx, cx = (a.left + a.right) / 2, cy = (a.top + a.bottom) / 2;
            ctx.save(); ctx.textAlign = "center";
            ctx.fillStyle = css("--text"); ctx.font = "700 24px 'Segoe UI', system-ui, sans-serif";
            ctx.textBaseline = "alphabetic"; ctx.fillText(opts.text, cx, cy + 6);
            ctx.fillStyle = css("--text-3"); ctx.font = "600 11px 'Segoe UI', system-ui, sans-serif";
            ctx.fillText(opts.sub || "", cx, cy + 24); ctx.restore();
        }
    };

    function baseOptions() {
        return {
            responsive: true, maintainAspectRatio: false,
            animation: { duration: 500 },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: css("--surface"), titleColor: css("--text"), bodyColor: css("--text-2"),
                    borderColor: css("--border"), borderWidth: 1, padding: 10, cornerRadius: 8, boxPadding: 4
                }
            }
        };
    }
    function axes(extra) {
        var grid = { color: css("--grid"), drawBorder: false }, tick = { color: css("--text-3") };
        return Object.assign({
            x: { grid: { display: false }, ticks: tick, border: { color: css("--border") } },
            y: { grid: grid, ticks: tick, beginAtZero: true, border: { display: false } }
        }, extra || {});
    }
    function legendOpts() {
        return { display: true, position: "top", align: "start",
                 labels: { color: css("--text-2"), usePointStyle: true, pointStyle: "rectRounded", boxWidth: 9, boxHeight: 9, padding: 14 } };
    }
    var configs = {};     // canvas id -> Chart config (kept so tables work before a chart is drawn)
    var firstDraw = {};   // canvas id -> true once its entrance animation has played
    var observer = null, seq = 0;

    // Entrance animation per chart type (plays once, when the chart scrolls into view)
    function entrance(config, order) {
        var t = config.type, delay = order * 90;
        var anim = { duration: 1100, easing: "easeOutQuart" };
        if (t === "doughnut") {
            anim = { duration: 1300, easing: "easeOutCubic", animateRotate: true, animateScale: true, delay: delay };
        } else if (t === "line") {
            // draw the line from left to right: each point starts after the previous one
            var n = config.data.datasets[0].data.length, per = Math.max(30, 1100 / Math.max(1, n));
            var prevY = function (ctx) { return ctx.chart.scales.y.getPixelForValue(0); };
            anim = {
                x: { type: "number", easing: "linear", duration: per, from: NaN,
                     delay: function (c) { if (c.type !== "data" || c.xStarted) return 0; c.xStarted = true; return delay + c.index * per; } },
                y: { type: "number", easing: "linear", duration: per, from: prevY,
                     delay: function (c) { if (c.type !== "data" || c.yStarted) return 0; c.yStarted = true; return delay + c.index * per; } }
            };
        } else {   // bars grow from the axis, one after another
            anim = { duration: 900, easing: "easeOutBack",
                     delay: function (c) { return c.type === "data" && c.mode === "default" ? delay + c.dataIndex * 60 + c.datasetIndex * 120 : 0; } };
        }
        config.options = config.options || {};
        config.options.animation = anim;
        return config;
    }

    function draw(id, animate) {
        var el = document.getElementById(id), cfg = configs[id];
        if (!el || !cfg) return;
        if (charts[id]) charts[id].destroy();
        var c = cfg;
        if (animate) c = entrance(cfg, seq++ % 4);
        else { c.options = c.options || {}; c.options.animation = false; }
        charts[id] = new Chart(el, c);
        firstDraw[id] = true;
    }

    function make(id, config, extra) {
        var el = document.getElementById(id);
        if (!el) return;
        configs[id] = config;
        if (extra) extras[id] = extra;
        if (firstDraw[id]) { draw(id, false); return; }          // theme change: redraw instantly
        if (charts[id]) return;
        var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (reduce || !("IntersectionObserver" in window)) { draw(id, false); return; }
        if (!observer) observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (en.isIntersecting) { observer.unobserve(en.target); draw(en.target.id, true); }
            });
        }, { threshold: 0.25 });
        observer.observe(el);
    }

    /* ---------- dashboard charts ---------- */
    function renderDashboard() {
        var D = window.dashboardData;
        if (!D) return;
        var surface = css("--surface"), accent = css("--accent");
        var statusColors = ["--st-pending", "--st-processing", "--st-shipped", "--st-delivered", "--st-cancelled"].map(css);
        var total = D.status.values.reduce(function (a, b) { return a + b; }, 0);

        // 1. Orders by status
        make("statusChart", {
            type: "doughnut", plugins: [centerText],
            data: { labels: D.status.labels, datasets: [{ data: D.status.values, backgroundColor: statusColors, borderColor: surface, borderWidth: 2, hoverOffset: 6 }] },
            options: Object.assign(baseOptions(), {
                cutout: "64%",
                plugins: Object.assign(baseOptions().plugins, {
                    centerText: { text: fmtInt(total), sub: "ORDERS" },
                    tooltip: Object.assign(baseOptions().plugins.tooltip, { callbacks: { label: function (c) {
                        return " " + c.label + ": " + fmtInt(c.parsed) + " (" + (c.parsed / total * 100).toFixed(1) + "%)"; } } })
                })
            })
        });

        // 2. Monthly sales trend + forecast (one axis: revenue)
        var T = D.trend;
        var hollow = T.revenue.map(function (_v, i) { return T.complete[i] ? accent : surface; });
        var datasets = [{
            label: "Net revenue", data: T.revenue, borderColor: accent, backgroundColor: accent, borderWidth: 2.5,
            tension: 0.28, pointRadius: 4, pointHoverRadius: 6, pointBackgroundColor: hollow, pointBorderColor: accent, pointBorderWidth: 2, spanGaps: false
        }];
        if (T.forecast) datasets.push({
            label: "Forecast (linear trend)", data: T.forecast, borderColor: accent, borderWidth: 2, borderDash: [6, 5],
            tension: 0, pointRadius: 4, pointStyle: "rectRot", pointBackgroundColor: surface, pointBorderColor: accent, pointBorderWidth: 2, spanGaps: false
        });
        var trendOpts = baseOptions();
        trendOpts.interaction = { mode: "index", intersect: false };
        trendOpts.plugins.legend = T.forecast ? legendOpts() : { display: false };
        trendOpts.plugins.tooltip.callbacks = {
            label: function (c) { return " " + c.dataset.label + ": " + peso(c.parsed.y); },
            afterBody: function (items) {
                var i = items[0].dataIndex, lines = [];
                if (T.orders[i] != null) lines.push("Orders: " + fmtInt(T.orders[i]));
                if (T.revenue[i] != null && !T.complete[i]) lines.push("Month still in progress");
                return lines;
            }
        };
        trendOpts.scales = axes({ y: { grid: { color: css("--grid") }, ticks: { color: css("--text-3"), callback: compact }, beginAtZero: true, border: { display: false } } });
        make("trendChart", { type: "line", data: { labels: T.labels, datasets: datasets }, options: trendOpts },
             { name: "Orders", values: T.orders });

        // 3. Top products (horizontal bars)
        var P = D.topProducts, po = baseOptions();
        po.indexAxis = "y"; po.layout = { padding: { right: 56 } };
        po.scales = axes({ x: { grid: { color: css("--grid") }, ticks: { color: css("--text-3"), callback: compact }, beginAtZero: true, border: { display: false } },
                           y: { grid: { display: false }, ticks: { color: css("--text-2") }, border: { color: css("--border") } } });
        po.plugins.barEndLabels = { format: function (v) { return compact(v); } };
        po.plugins.tooltip.callbacks = { label: function (c) { return " " + peso(c.parsed.x) + " · " + fmtInt(P.units[c.dataIndex]) + " units"; } };
        make("topProductsChart", { type: "bar", plugins: [barEndLabels],
            data: { labels: P.labels, datasets: [{ label: "Revenue", data: P.values, backgroundColor: accent, borderRadius: 4, borderSkipped: false, barPercentage: 0.72 }] }, options: po });

        // 4. Revenue by category
        var C = D.category, co = baseOptions();
        co.indexAxis = "y"; co.layout = { padding: { right: 78 } };
        co.scales = po.scales;
        co.plugins.barEndLabels = { format: function (v, i) { return compact(v) + " · " + C.share[i] + "%"; } };
        co.plugins.tooltip.callbacks = { label: function (c) { return " " + peso(c.parsed.x) + " (" + C.share[c.dataIndex] + "% of revenue)"; } };
        make("categoryChart", { type: "bar", plugins: [barEndLabels],
            data: { labels: C.labels, datasets: [{ label: "Revenue", data: C.values, backgroundColor: accent, borderRadius: 4, borderSkipped: false, barPercentage: 0.72 }] }, options: co });

        // 5. Status mix per month (stacked, 2px surface gaps)
        var SM = D.statusMonth, so = baseOptions();
        so.interaction = { mode: "index", intersect: false };
        so.plugins.legend = legendOpts();
        so.scales = axes({ x: { stacked: true, grid: { display: false }, ticks: { color: css("--text-3") }, border: { color: css("--border") } },
                           y: { stacked: true, grid: { color: css("--grid") }, ticks: { color: css("--text-3") }, beginAtZero: true, border: { display: false } } });
        make("statusMonthChart", { type: "bar",
            data: { labels: SM.labels, datasets: ["Pending", "Processing", "Shipped", "Delivered", "Cancelled"].map(function (s, i) {
                return { label: s, data: SM.series[s], backgroundColor: statusColors[i], borderColor: surface, borderWidth: 2, borderRadius: 0, borderSkipped: false }; }) },
            options: so });

        // 6. Orders by weekday
        var W = D.weekday, wo = baseOptions();
        wo.layout = { padding: { top: 18 } };
        wo.scales = axes();
        wo.plugins.barEndLabels = { format: function (v) { return fmtInt(v); } };
        wo.plugins.tooltip.callbacks = { title: function (it) { return W.names[it[0].dataIndex]; }, label: function (c) { return " " + fmtInt(c.parsed.y) + " orders"; } };
        make("weekdayChart", { type: "bar", plugins: [barEndLabels],
            data: { labels: W.labels, datasets: [{ label: "Orders", data: W.values, backgroundColor: accent, borderRadius: 4, borderSkipped: false, barPercentage: 0.7 }] }, options: wo });

        // 7. Order-value histogram
        var H = D.hist, ho = baseOptions();
        ho.layout = { padding: { top: 18 } };
        ho.scales = axes();
        ho.scales.x.title = { display: true, text: "Order value (₱)", color: css("--text-3") };
        ho.scales.y.title = { display: true, text: "Orders", color: css("--text-3") };
        ho.scales.x.ticks = { color: css("--text-3"), maxRotation: 40, minRotation: 0 };
        ho.plugins.barEndLabels = { format: function (v) { return v ? fmtInt(v) : ""; } };
        ho.plugins.tooltip.callbacks = { title: function (it) { return "₱" + H.labels[it[0].dataIndex]; }, label: function (c) { return " " + fmtInt(c.parsed.y) + " orders"; } };
        make("histChart", { type: "bar", plugins: [barEndLabels],
            data: { labels: H.labels, datasets: [{ label: "Orders", data: H.values, backgroundColor: accent, borderRadius: 3, borderSkipped: false, barPercentage: 1, categoryPercentage: 0.94 }] }, options: ho });
    }

    /* ---------- risk page charts ---------- */
    function renderRisk() {
        var R = window.riskData;
        if (!R) return;
        var surface = css("--surface"), accent = css("--accent");
        var colors = ["--lv-high", "--lv-medium", "--lv-low"].map(css);
        var total = R.levels.values.reduce(function (a, b) { return a + b; }, 0);
        make("riskLevelChart", {
            type: "doughnut", plugins: [centerText],
            data: { labels: R.levels.labels.map(function (l) { return l + " risk"; }), datasets: [{ data: R.levels.values, backgroundColor: colors, borderColor: surface, borderWidth: 2, hoverOffset: 6 }] },
            options: Object.assign(baseOptions(), { cutout: "64%", plugins: Object.assign(baseOptions().plugins, { centerText: { text: fmtInt(total), sub: "OPEN ORDERS" } }) })
        });
        var ao = baseOptions(); ao.layout = { padding: { top: 18 } }; ao.scales = axes();
        ao.plugins.barEndLabels = { format: function (v) { return fmtInt(v); } };
        make("riskAgeChart", { type: "bar", plugins: [barEndLabels],
            data: { labels: R.ages.labels, datasets: [{ label: "Open orders", data: R.ages.values, backgroundColor: accent, borderRadius: 4, borderSkipped: false, barPercentage: 0.7 }] }, options: ao });
    }

    function renderAll() {
        if (typeof Chart === "undefined") return;
        Chart.defaults.font.family = "'Segoe UI', system-ui, -apple-system, sans-serif";
        Chart.defaults.color = css("--text-2");
        renderDashboard(); renderRisk(); buildTables();
    }

    /* ---------- accessible table view for every chart ---------- */
    function buildTables() {
        document.querySelectorAll("[data-chartcard]").forEach(function (card) {
            var canvas = card.querySelector("canvas"), holder = card.querySelector(".chart-table");
            if (!canvas || !holder || !configs[canvas.id]) return;
            var ch = configs[canvas.id], ex = extras[canvas.id];
            var head = "<th>Category</th>" + ch.data.datasets.map(function (d) { return "<th class='r'>" + d.label + "</th>"; }).join("") + (ex ? "<th class='r'>" + ex.name + "</th>" : "");
            var rows = ch.data.labels.map(function (l, i) {
                return "<tr><td>" + l + "</td>" + ch.data.datasets.map(function (d) {
                    var v = d.data[i]; return "<td class='r'>" + (v == null ? "—" : Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 })) + "</td>"; }).join("") +
                    (ex ? "<td class='r'>" + (ex.values[i] == null ? "—" : fmtInt(ex.values[i])) + "</td>" : "") + "</tr>";
            }).join("");
            holder.innerHTML = "<table><thead><tr>" + head + "</tr></thead><tbody>" + rows + "</tbody></table>";
        });
    }
    document.querySelectorAll(".tbl-toggle").forEach(function (b) {
        b.addEventListener("click", function () {
            var card = b.closest(".card"); card.classList.toggle("show-table");
            b.textContent = card.classList.contains("show-table") ? "Chart" : "Table";
        });
    });

    /* ---------- theme toggle ---------- */
    var themeBtn = document.getElementById("themeBtn");
    if (themeBtn) themeBtn.addEventListener("click", function () {
        var root = document.documentElement, cur = root.getAttribute("data-theme");
        if (!cur) cur = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
        var next = cur === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        try { localStorage.setItem("op-theme", next); } catch (e) {}
        renderAll();
    });
    if (window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () { setTimeout(renderAll, 50); });

    /* ---------- filter presets ---------- */
    var form = document.getElementById("filterForm");
    if (form && form.dataset.max) {
        form.querySelectorAll(".presets .chip").forEach(function (chip) {
            chip.addEventListener("click", function () {
                var max = new Date(form.dataset.max + "T00:00:00"), d = chip.dataset.days, start = "", end = "";
                function iso(x) { return x.getFullYear() + "-" + String(x.getMonth() + 1).padStart(2, "0") + "-" + String(x.getDate()).padStart(2, "0"); }
                if (d === "all") { start = ""; end = ""; }
                else if (d === "ytd") { start = max.getFullYear() + "-01-01"; end = form.dataset.max; }
                else { var s = new Date(max); s.setDate(s.getDate() - (parseInt(d, 10) - 1)); start = iso(s); end = form.dataset.max; }
                form.elements.start.value = start; form.elements.end.value = end; form.submit();
            });
        });
    }


    /* ---------- animated header: moving particles ---------- */
    (function headerParticles() {
        var cv = document.getElementById("headerFX");
        if (!cv || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) return;
        var ctx = cv.getContext("2d"), dots = [], W = 0, H = 0, dpr = Math.min(2, window.devicePixelRatio || 1), mouse = null;
        function size() {
            var r = cv.getBoundingClientRect(); W = r.width; H = r.height;
            cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            var n = Math.max(18, Math.min(70, Math.round(W / 22)));
            while (dots.length < n) dots.push({ x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - .5) * .5, vy: (Math.random() - .5) * .35, r: Math.random() * 1.8 + .8, a: Math.random() * .5 + .3 });
            dots.length = n;
        }
        function step() {
            ctx.clearRect(0, 0, W, H);
            for (var i = 0; i < dots.length; i++) {
                var p = dots[i];
                p.x += p.vx; p.y += p.vy;
                if (p.x < -5) p.x = W + 5; else if (p.x > W + 5) p.x = -5;
                if (p.y < -5) p.y = H + 5; else if (p.y > H + 5) p.y = -5;
                ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 6.2832);
                ctx.fillStyle = "rgba(255,255,255," + p.a + ")"; ctx.fill();
                for (var j = i + 1; j < dots.length; j++) {
                    var q = dots[j], dx = p.x - q.x, dy = p.y - q.y, d = dx * dx + dy * dy;
                    if (d < 6400) {
                        ctx.strokeStyle = "rgba(255,255,255," + (0.22 * (1 - d / 6400)) + ")"; ctx.lineWidth = 1;
                        ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
                    }
                }
                if (mouse) {                                   // particles gently drift away from the cursor
                    var mx = p.x - mouse.x, my = p.y - mouse.y, md = mx * mx + my * my;
                    if (md < 5000 && md > 1) { p.x += mx / Math.sqrt(md) * .8; p.y += my / Math.sqrt(md) * .8; }
                }
            }
            if (!document.hidden) requestAnimationFrame(step); else setTimeout(function () { requestAnimationFrame(step); }, 400);
        }
        cv.parentElement.addEventListener("mousemove", function (e) { var r = cv.getBoundingClientRect(); mouse = { x: e.clientX - r.left, y: e.clientY - r.top }; });
        cv.parentElement.addEventListener("mouseleave", function () { mouse = null; });
        window.addEventListener("resize", size);
        size(); step();
    })();

    /* ---------- upload dropzone ---------- */
    var drop = document.getElementById("drop"), input = document.getElementById("fileInput");
    if (drop && input) {
        ["dragenter", "dragover"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); }); });
        ["dragleave", "drop"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); }); });
        drop.addEventListener("drop", function (e) { if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; input.dispatchEvent(new Event("change")); } });
        input.addEventListener("change", function () {
            if (input.files.length) document.getElementById("dropText").textContent = input.files[0].name + " (" + Math.round(input.files[0].size / 1024) + " KB)";
        });
    }

    /* ---------- SQL syntax highlighting + copy ---------- */
    var KW = "SELECT|FROM|WHERE|AND|OR|NOT|GROUP BY|ORDER BY|HAVING|LIMIT|AS|WITH|OVER|PARTITION BY|CASE|WHEN|THEN|ELSE|END|IN|DESC|ASC|DISTINCT|JOIN|ON|LEFT|CREATE|TABLE|VIEW|INDEX|CHECK|NULL|PRIMARY KEY|INTEGER|TEXT|REAL|UNIQUE|AUTOINCREMENT|INSERT|INTO|VALUES";
    var FN = "COUNT|SUM|AVG|MIN|MAX|ROUND|CAST|RANK|LAG|COALESCE|strftime|julianday";
    var re = new RegExp("('[^']*')|(--[^\\n]*)|\\b(" + KW + ")\\b|\\b(" + FN + ")(?=\\()", "gi");
    function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
    document.querySelectorAll("pre.sql-text").forEach(function (pre) {
        var raw = pre.textContent;
        pre.innerHTML = esc(raw).replace(new RegExp(re.source.replace("[^']", "[^']"), "gi"), function (m, str, cm, kw, fn) {
            if (str) return "<span class='str'>" + str + "</span>";
            if (cm) return "<span class='cm'>" + cm + "</span>";
            if (kw) return "<span class='kw'>" + kw + "</span>";
            if (fn) return "<span class='fn'>" + fn + "</span>";
            return m;
        });
        var btn = pre.parentElement.querySelector(".copy");
        if (btn) btn.addEventListener("click", function () {
            try { navigator.clipboard.writeText(raw); btn.textContent = "Copied ✓"; setTimeout(function () { btn.textContent = "Copy"; }, 1400); } catch (e) { btn.textContent = "Press Ctrl+C"; }
        });
    });

    document.addEventListener("DOMContentLoaded", renderAll);
    if (document.readyState !== "loading") renderAll();
})();
