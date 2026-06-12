/* =======================================================================
   Anda Lava · POS — Comportamiento de la pantalla de acceso
   - Mostrar / ocultar contraseña.
   - Validación básica en el cliente ANTES del envío (sin romper el POST).
   - Micro-feedback al enfocar y al enviar.
   El servidor (LoginView) sigue siendo la fuente de verdad de la autenticación.
   ======================================================================= */
(function () {
    "use strict";

    var form = document.getElementById("login-form");
    if (!form) return;

    var username = form.querySelector("#username");
    var password = form.querySelector("#password");
    var button = form.querySelector(".btn");
    var toggle = form.querySelector("[data-toggle-password]");
    var inputs = [username, password];

    /* ---------- Mostrar / ocultar contraseña ---------- */
    if (toggle && password) {
        toggle.addEventListener("click", function () {
            var reveal = password.type === "password";
            password.type = reveal ? "text" : "password";
            toggle.textContent = reveal ? "Ocultar" : "Ver";
            toggle.setAttribute("aria-pressed", String(reveal));
            password.focus();
        });
    }

    /* ---------- Limpia el estado de error al escribir ---------- */
    function setFieldError(input, hasError) {
        var field = input.closest(".field");
        if (field) field.classList.toggle("field--error", hasError);
    }

    inputs.forEach(function (input) {
        if (!input) return;
        input.addEventListener("input", function () {
            setFieldError(input, false);
        });
    });

    /* ---------- Validación de cliente al enviar ---------- */
    form.addEventListener("submit", function (event) {
        var firstInvalid = null;

        inputs.forEach(function (input) {
            if (!input) return;
            var empty = input.value.trim() === "";
            setFieldError(input, empty);
            if (empty && !firstInvalid) firstInvalid = input;
        });

        if (firstInvalid) {
            event.preventDefault();             // no enviamos si falta algún dato
            firstInvalid.focus();
            // re-disparar la animación de sacudida
            form.classList.remove("shake");
            void form.offsetWidth;
            form.classList.add("shake");
            return;
        }

        // Datos completos: dejamos que el POST continúe y damos feedback visual.
        if (button) button.classList.add("is-loading");
    });
})();

/* =======================================================================
   Anda Lava · POS — Shell de la aplicación
   Módulos independientes; cada uno se auto-desactiva si su página no está
   presente. Nada de lógica incrustada en los templates: el HTML solo declara
   datos (atributos data-* y bloques <script type="application/json"> creados
   con el filtro |json_script de Django) y aquí se les da comportamiento.
   ======================================================================= */

/* ---------------- Módulo: navegación lateral en móvil ----------------- */
(function () {
    "use strict";

    var shell = document.getElementById("shell");
    var toggle = document.querySelector("[data-nav-toggle]");
    var scrim = document.querySelector("[data-nav-scrim]");
    if (!shell || !toggle || !scrim) return;

    function setOpen(open) {
        shell.classList.toggle("nav-open", open);
        toggle.setAttribute("aria-expanded", String(open));
        scrim.hidden = !open;
    }

    toggle.addEventListener("click", function () {
        setOpen(!shell.classList.contains("nav-open"));
    });
    scrim.addEventListener("click", function () { setOpen(false); });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") setOpen(false);
    });
    // Al navegar desde el menú, se cierra para no quedar abierto al volver.
    shell.querySelectorAll(".nav__link").forEach(function (link) {
        link.addEventListener("click", function () { setOpen(false); });
    });
})();

/* --------------- Módulo: filtro instantáneo de tablas ----------------- */
/* Complementa (no sustituye) la búsqueda del servidor: mientras el usuario
   teclea, oculta filas de la página actual; al enviar el form, busca en BD. */
(function () {
    "use strict";

    document.querySelectorAll("input[data-table-filter]").forEach(function (input) {
        var table = document.querySelector(input.getAttribute("data-table-filter"));
        if (!table) return;
        var rows = table.querySelectorAll("tbody tr");

        input.addEventListener("input", function () {
            var term = input.value.trim().toLowerCase();
            rows.forEach(function (row) {
                row.hidden = term !== "" && row.textContent.toLowerCase().indexOf(term) === -1;
            });
        });
    });
})();

/* ------------------- Módulo: gráficas del dashboard ------------------- */
/* Los datos del tenant llegan en el JSON seguro #dashboard-data (generado
   por |json_script); los <canvas data-chart="..."> solo son lienzos vacíos. */
(function () {
    "use strict";

    var dataNode = document.getElementById("dashboard-data");
    if (!dataNode || typeof window.Chart === "undefined") return;

    var payload = JSON.parse(dataNode.textContent);
    var money = new Intl.NumberFormat("es-MX", { style: "currency", currency: payload.currency || "MXN" });

    // Identidad visual de marca para TODAS las gráficas.
    var BLUE = "#1E50C8";
    var INK_SOFT = "#6B7C8E";
    var GRID = "rgba(30, 80, 200, .08)";
    Chart.defaults.font.family = "'JetBrains Mono', ui-monospace, monospace";
    Chart.defaults.font.size = 11;
    Chart.defaults.color = INK_SOFT;

    function emptyMessage(canvas, text) {
        var holder = canvas.parentElement;
        var p = document.createElement("p");
        p.className = "panel__empty";
        p.textContent = text;
        holder.replaceChildren(p);
    }

    /* Inicialización idempotente: si el <canvas> ya tiene una instancia viva
       (doble carga del script, restauración bfcache al navegar con filtros),
       se destruye ANTES de crear la nueva. Chart.js pinta encimado si no. */
    function freshCanvas(canvas) {
        var previous = Chart.getChart(canvas);
        if (previous) previous.destroy();
        return canvas;
    }

    /* --- Ventas del periodo (barras; el servidor decide el rango) --- */
    var salesCanvas = document.querySelector("[data-chart='sales-week']");
    if (salesCanvas) {
        new Chart(freshCanvas(salesCanvas), {
            type: "bar",
            data: {
                labels: payload.salesSeries.labels,
                datasets: [{
                    data: payload.salesSeries.values,
                    backgroundColor: "rgba(30, 80, 200, .82)",
                    hoverBackgroundColor: BLUE,
                    borderRadius: 7,
                    borderSkipped: false,
                    maxBarThickness: 42
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "#0E1A2B",
                        padding: 12,
                        cornerRadius: 8,
                        displayColors: false,
                        callbacks: {
                            label: function (ctx) { return money.format(ctx.parsed.y); }
                        }
                    }
                },
                scales: {
                    x: { grid: { display: false }, border: { color: GRID } },
                    y: {
                        beginAtZero: true,
                        grid: { color: GRID },
                        border: { display: false },
                        ticks: {
                            callback: function (value) { return "$" + Number(value).toLocaleString("es-MX"); }
                        }
                    }
                }
            }
        });
    }

    /* --- Categorías más solicitadas (barras horizontales) --- */
    var catCanvas = document.querySelector("[data-chart='top-categories']");
    if (catCanvas) {
        var labels = payload.topCategories.labels;
        if (!labels.length) {
            emptyMessage(catCanvas, "No hay ventas en el periodo seleccionado.");
        } else {
            new Chart(freshCanvas(catCanvas), {
                type: "bar",
                data: {
                    labels: labels,
                    datasets: [{
                        data: payload.topCategories.values,
                        backgroundColor: labels.map(function (_, i) {
                            return "rgba(30, 80, 200, " + Math.max(0.25, 0.9 - i * 0.13).toFixed(2) + ")";
                        }),
                        borderRadius: 6,
                        borderSkipped: false,
                        maxBarThickness: 26
                    }]
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: "#0E1A2B",
                            padding: 12,
                            cornerRadius: 8,
                            displayColors: false,
                            callbacks: {
                                label: function (ctx) { return ctx.parsed.x + " pzas vendidas"; }
                            }
                        }
                    },
                    scales: {
                        x: { beginAtZero: true, grid: { color: GRID }, border: { display: false }, ticks: { precision: 0 } },
                        y: { grid: { display: false }, border: { display: false } }
                    }
                }
            });
        }
    }

    /* --- Cobrado vs por cobrar (dona financiera) --- */
    var incomeCanvas = document.querySelector("[data-chart='income-status']");
    if (incomeCanvas) {
        var income = payload.incomeStatus || { labels: [], values: [] };
        var hasIncome = income.values.some(function (value) { return value > 0; });
        if (!hasIncome) {
            emptyMessage(incomeCanvas, "Aún no hay movimientos financieros que graficar.");
        } else {
            new Chart(freshCanvas(incomeCanvas), {
                type: "doughnut",
                data: {
                    labels: income.labels,
                    datasets: [{
                        data: income.values,
                        // Azul de marca = dinero en caja; ámbar = saldo en anaquel.
                        backgroundColor: ["rgba(30, 80, 200, .85)", "rgba(185, 126, 20, .7)"],
                        hoverBackgroundColor: [BLUE, "#B97E14"],
                        borderWidth: 0,
                        hoverOffset: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: "66%",
                    plugins: {
                        legend: {
                            position: "bottom",
                            labels: { boxWidth: 10, boxHeight: 10, padding: 14 }
                        },
                        tooltip: {
                            backgroundColor: "#0E1A2B",
                            padding: 12,
                            cornerRadius: 8,
                            displayColors: false,
                            callbacks: {
                                label: function (ctx) {
                                    return ctx.label + ": " + money.format(ctx.parsed);
                                }
                            }
                        }
                    }
                }
            });
        }
    }
})();

/* ----------------------- Módulo: punto de venta ----------------------- */
/* El estado del ticket vive aquí, pero SIEMPRE se materializa como inputs
   ocultos del inline formset de Django (details-N-product / -quantity):
   el envío es un POST clásico que el backend re-valida contra el tenant.
   Si el servidor rechaza la venta, los mismos inputs re-hidratan el ticket. */
(function () {
    "use strict";

    var form = document.getElementById("pos-form");
    if (!form) return;

    var grid = form.querySelector("[data-pos-grid]");
    var linesEl = form.querySelector("[data-pos-lines]");
    var emptyEl = form.querySelector("[data-pos-empty]");
    var totalEl = form.querySelector("[data-pos-total]");
    var inputsEl = form.querySelector("[data-pos-inputs]");
    var submitBtn = form.querySelector("[data-pos-submit]");
    var totalForms = form.querySelector("input[name$='-TOTAL_FORMS']");
    var noResults = form.querySelector("[data-pos-noresults]");
    if (!grid || !linesEl || !inputsEl || !totalForms) return;

    var prefix = totalForms.name.replace("-TOTAL_FORMS", "");
    var money = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" });

    /* Saldo restante en vivo: total del ticket menos el anticipo tecleado. */
    var partialInput = form.querySelector("input[name='partial_payment']");
    var dueRow = form.querySelector("[data-pos-due-row]");
    var dueEl = form.querySelector("[data-pos-due]");
    var currentTotal = 0;

    function updateDue() {
        if (!dueRow || !dueEl) return;
        var partial = partialInput ? parseFloat(partialInput.value) : 0;
        if (isNaN(partial) || partial < 0) partial = 0;
        var due = Math.max(currentTotal - partial, 0);
        dueRow.hidden = partial <= 0;
        dueEl.textContent = money.format(due);
        // Aviso visual si el anticipo excede el total (el servidor lo rechaza).
        dueRow.classList.toggle("pos__due--excess", partial > currentTotal);
    }

    if (partialInput) partialInput.addEventListener("input", updateDue);

    /* Catálogo: las tarjetas server-rendered son la fuente de verdad. */
    var cards = {};
    grid.querySelectorAll(".pos-card").forEach(function (card) {
        cards[card.dataset.product] = card;
    });

    /* Estado del ticket: [{id, qty}] en orden de captura. */
    var lines = [];

    function findLine(id) {
        for (var i = 0; i < lines.length; i++) if (lines[i].id === id) return lines[i];
        return null;
    }

    /* Re-hidratación: si el POST fue rechazado, Django re-pinta los inputs
       ocultos del formset y de ahí reconstruimos el ticket en pantalla. */
    inputsEl.querySelectorAll("input[name$='-product']").forEach(function (input) {
        var index = input.name.slice(prefix.length + 1).split("-")[0];
        var qtyInput = form.querySelector("input[name='" + prefix + "-" + index + "-quantity']");
        var id = input.value;
        var qty = qtyInput ? parseInt(qtyInput.value, 10) : 1;
        if (!id || !cards[id] || isNaN(qty) || qty < 1) return;  // ids ajenos se descartan
        var line = findLine(id);
        if (line) { line.qty += qty; } else { lines.push({ id: id, qty: qty }); }
    });

    /* ------------------------- Render ------------------------------- */
    function lineRow(line) {
        var card = cards[line.id];
        var price = parseFloat(card.dataset.price);
        var li = document.createElement("li");
        li.className = "pos-line";

        var name = document.createElement("div");
        var title = document.createElement("span");
        title.className = "pos-line__name";
        title.textContent = card.dataset.name;
        var each = document.createElement("span");
        each.className = "pos-line__each";
        each.textContent = money.format(price) + " c/u";
        name.appendChild(title);
        name.appendChild(each);

        var qty = document.createElement("span");
        qty.className = "pos-line__qty";
        ["-", "+"].forEach(function (sign, i) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "pos-line__btn";
            btn.dataset.id = line.id;
            btn.dataset.action = i === 0 ? "minus" : "plus";
            btn.textContent = sign;
            btn.setAttribute("aria-label", (i === 0 ? "Quitar una pieza de " : "Agregar una pieza de ") + card.dataset.name);
            if (i === 0) qty.appendChild(btn);
            else {
                var count = document.createElement("span");
                count.className = "pos-line__count";
                count.textContent = line.qty;
                qty.appendChild(count);
                qty.appendChild(btn);
            }
        });

        var amount = document.createElement("span");
        amount.className = "pos-line__amount";
        amount.textContent = money.format(price * line.qty);

        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "pos-line__remove";
        remove.dataset.id = line.id;
        remove.dataset.action = "remove";
        remove.textContent = "Quitar";

        li.appendChild(name);
        li.appendChild(qty);
        li.appendChild(amount);
        li.appendChild(remove);
        return li;
    }

    function hiddenInput(name, value) {
        var input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.value = value;
        return input;
    }

    function render() {
        var total = 0;

        linesEl.replaceChildren();
        inputsEl.replaceChildren();

        lines.forEach(function (line, index) {
            total += parseFloat(cards[line.id].dataset.price) * line.qty;
            linesEl.appendChild(lineRow(line));
            // Materializa la línea como formset de Django (índices compactos).
            inputsEl.appendChild(hiddenInput(prefix + "-" + index + "-product", line.id));
            inputsEl.appendChild(hiddenInput(prefix + "-" + index + "-quantity", line.qty));
        });

        totalForms.value = lines.length;
        currentTotal = total;
        if (totalEl) totalEl.textContent = money.format(total);
        if (emptyEl) emptyEl.hidden = lines.length > 0;
        if (submitBtn) submitBtn.disabled = lines.length === 0;
        updateDue();
    }

    /* ------------------------ Interacción --------------------------- */
    grid.addEventListener("click", function (event) {
        var card = event.target.closest(".pos-card");
        if (!card) return;
        var line = findLine(card.dataset.product);
        if (line) line.qty += 1;
        else lines.push({ id: card.dataset.product, qty: 1 });

        card.classList.remove("pos-card--added");
        void card.offsetWidth;                       // re-dispara la animación
        card.classList.add("pos-card--added");
        render();
    });

    linesEl.addEventListener("click", function (event) {
        var btn = event.target.closest("button[data-action]");
        if (!btn) return;
        var line = findLine(btn.dataset.id);
        if (!line) return;

        if (btn.dataset.action === "plus") line.qty += 1;
        if (btn.dataset.action === "minus") line.qty -= 1;
        if (btn.dataset.action === "remove" || line.qty < 1) {
            lines = lines.filter(function (l) { return l.id !== line.id; });
        }
        render();
    });

    /* --------------- Búsqueda y filtro por categoría ----------------- */
    var search = form.querySelector("[data-pos-search]");
    var chipBox = form.querySelector("[data-pos-categories]");
    var activeCategory = "all";

    function applyFilters() {
        var term = search ? search.value.trim().toLowerCase() : "";
        var visible = 0;
        Object.keys(cards).forEach(function (id) {
            var card = cards[id];
            var matchesTerm = term === "" || card.dataset.name.toLowerCase().indexOf(term) !== -1;
            var matchesCat = activeCategory === "all" || card.dataset.category === activeCategory;
            var show = matchesTerm && matchesCat;
            card.classList.toggle("is-hidden", !show);
            if (show) visible++;
        });
        if (noResults) noResults.hidden = visible > 0;
    }

    if (search) search.addEventListener("input", applyFilters);
    if (chipBox) {
        chipBox.addEventListener("click", function (event) {
            var chip = event.target.closest(".chip");
            if (!chip) return;
            chipBox.querySelectorAll(".chip").forEach(function (c) { c.classList.remove("is-active"); });
            chip.classList.add("is-active");
            activeCategory = chip.dataset.category;
            applyFilters();
        });
    }

    render();   // pinta el estado inicial (vacío o re-hidratado tras un error)
})();

/* --------------- Módulo: UX de la barra de filtros -------------------- */
/* El periodo predefinido y el rango manual son alternativos: elegir uno
   limpia el otro para que la QueryString enviada sea inequívoca. El envío
   y el botón "Eliminar filtros" son HTML puro (GET + <a>): esto es solo
   comodidad de captura, el panel funciona idéntico sin JavaScript. */
(function () {
    "use strict";

    var form = document.querySelector("[data-filter-form]");
    if (!form) return;

    var period = form.querySelector("[data-filter-period]");
    var dates = form.querySelectorAll("[data-filter-date]");

    if (period) {
        period.addEventListener("change", function () {
            if (period.value === "") return;
            dates.forEach(function (input) { input.value = ""; });
        });
    }
    dates.forEach(function (input) {
        input.addEventListener("input", function () {
            if (input.value !== "" && period) period.value = "";
        });
    });
})();

/* --------------------- Módulo: imprimir recibo ------------------------ */
(function () {
    "use strict";

    document.querySelectorAll("[data-print]").forEach(function (button) {
        button.addEventListener("click", function () { window.print(); });
    });
})();
