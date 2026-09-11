/* Ausbruch-Werkstatt - Oberflaechenlogik.
   Haelt keinen eigenen Zustand ueber den Lauf: alles kommt ueber den
   Live-Strom vom Server. Ein Neuladen der Seite waehrend eines Laufs
   verliert deshalb nichts ausser dem bereits gezeigten Protokoll. */

const $  = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let FELDER = [];
let LAEUFT = false;
let LETZTER_LAUF = null;

/* ---------- Formatierung ---------- */
const nz = (x, n = 2) =>
  (x === null || x === undefined || Number.isNaN(x)) ? "–" :
  Number(x).toLocaleString("de-DE", { minimumFractionDigits: n, maximumFractionDigits: n });
const geld = (x) => (x === null || x === undefined) ? "–" : "$" + nz(x, 0);
const pct  = (x, n = 2) => (x === null || x === undefined) ? "–" : nz(x, n) + " %";
const farbe = (x) => x > 0 ? "gut" : (x < 0 ? "schlecht" : "");

/* ---------- Protokoll ---------- */
function log(text, stufe = "info") {
  const kasten = $("#log");
  const z = document.createElement("div");
  const t = new Date().toLocaleTimeString("de-DE");
  z.className = "z-" + stufe;
  z.innerHTML = `<span class="z-zeit">${t}</span>  ` +
                text.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  kasten.appendChild(z);
  while (kasten.childElementCount > 600) kasten.removeChild(kasten.firstChild);
  kasten.scrollTop = kasten.scrollHeight;
}

/* ---------- Einstellungsfelder aufbauen ---------- */
function felderBauen(felder, vorgaben) {
  FELDER = felder;
  const ziel = $("#felder");
  ziel.innerHTML = "";
  const gruppen = [...new Set(felder.map(f => f.gruppe))];

  for (const g of gruppen) {
    const fs = document.createElement("fieldset");
    fs.innerHTML = `<legend>${g}</legend>`;
    for (const f of felder.filter(x => x.gruppe === g)) {
      const wrap = document.createElement("label");
      const wert = vorgaben[f.name];
      if (f.schalter) {
        wrap.innerHTML =
          `<input type="checkbox" id="f-${f.name}" ${wert ? "checked" : ""}
                  style="width:auto;margin-right:8px"> ${f.label}` +
          (f.hilfe ? `<p class="feld-hilfe">${f.hilfe}</p>` : "");
      } else {
        const schritt = f.ganzzahl ? "1" : "any";
        wrap.innerHTML =
          `${f.label} <span class="einheit">${f.einheit ? "(" + f.einheit + ")" : ""}</span>
           <input type="number" id="f-${f.name}" value="${wert}"
                  min="${f.min}" max="${f.max}" step="${schritt}">` +
          (f.hilfe ? `<p class="feld-hilfe">${f.hilfe}</p>` : "");
      }
      fs.appendChild(wrap);
    }
    ziel.appendChild(fs);
  }
  $$("#felder input").forEach(i => i.addEventListener("input", vorschau));
  vorschau();
}

function configLesen() {
  const cfg = {};
  for (const f of FELDER) {
    const el = $("#f-" + f.name);
    if (!el) continue;
    cfg[f.name] = f.schalter ? el.checked : Number(el.value);
  }
  return cfg;
}

/* ---------- Kostenvorschau: die Zahl VOR dem Lauf ---------- */
function vorschau() {
  const c = configLesen();
  if (!c.halten_bars) return;
  const kostenRundlauf = (c.spanne_bps + 2 * c.slippage_bps) / 100;
  const rundlaeufe = 252 * 26 / c.halten_bars;
  const last = rundlaeufe * kostenRundlauf;
  const belegt = (c.positions_pct * c.max_positionen);

  let warnung = "";
  if (belegt > 100)
    warnung += `<br><b>Achtung:</b> ${c.max_positionen} Positionen zu je
      ${c.positions_pct} % sind ${nz(belegt,0)} % des Depots &ndash; mehr als vorhanden.
      Die Obergrenze greift, es werden weniger Positionen als eingestellt.`;
  if (c.verlust_pct === 0 && c.trailing_pct === 0)
    warnung += `<br><b>Kein Stop gesetzt.</b> Nur die Haltedauer begrenzt den Verlust.`;
  if (c.spanne_bps < 12)
    warnung += `<br><b>Spanne unter 12,2 bps</b> &ndash; das ist optimistischer als
      der gemessene Median des liquiden Universums, und Ausbruchskandidaten sind
      weiter als der Median.`;

  $("#kostenvorschau").innerHTML =
    `Ein Rundlauf kostet <b>${nz(kostenRundlauf, 3)} %</b>.
     Bei ${c.halten_bars} Bars Haltedauer sind das rund
     <b>${nz(rundlaeufe, 0)} Rundl&auml;ufe</b> pro Jahr und Positionsplatz
     = <b>${nz(last, 0)} % Kostenlast</b> j&auml;hrlich.
     Das muss die Strategie erst verdienen.${warnung}`;
}

/* ---------- Live-Strom ---------- */
function stromVerbinden() {
  const es = new EventSource("/api/strom");
  es.onmessage = (e) => {
    const n = JSON.parse(e.data);
    if (n.art === "log") log(n.text, n.stufe);
    else if (n.art === "fortschritt") {
      const p = Math.max(0, Math.min(100, n.anteil * 100));
      $("#balken").style.width = p + "%";
      $("#balken-text").textContent = `${p.toFixed(1)} %  —  ${n.text}`;
    }
    else if (n.art === "zustand") zustandZeigen(n);
    else if (n.art === "lauf_start") {
      LETZTER_LAUF = n.lauf_id;
      $("#k-versuche").textContent = n.n_versuche;
      $("#k-schwelle").textContent = nz(n.schwelle, 2);
      $("#ergebnisblock").hidden = true;
    }
    else if (n.art === "ergebnis") ergebnisZeigen(n);
    else if (n.art === "ende") {
      laufModus(false);
      if (n.grund === "daten") standHolen();
      tabsNeu();
    }
  };
  es.onerror = () => log("Verbindung zum Server unterbrochen – Seite neu laden.", "fehler");
}

function zustandZeigen(z) {
  $("#l-kapital").textContent = geld(z.kapital);
  const g = $("#l-gewinn");
  g.textContent = `${z.gewinn_usd >= 0 ? "+" : ""}${nz(z.gewinn_usd, 0)} $ (${nz(z.gewinn_pct, 2)} %)`;
  g.className = "k-wert " + farbe(z.gewinn_usd);
  $("#l-trades").textContent = z.n_trades;
  $("#l-offen").textContent = z.offene_positionen;
  $("#l-treffer").textContent = pct(z.trefferquote_pct, 1);
  $("#l-zeit").textContent = (z.zeitpunkt || "").slice(0, 16).replace("T", " ");
}

/* ---------- Ergebnis ---------- */
function ergebnisZeigen(n) {
  const k = n.kennzahlen;
  const ueber = k.t_wert !== null && Math.abs(k.t_wert) > n.schwelle;
  const kacheln = [
    ["Rendite",        pct(k.rendite_pct),            farbe(k.rendite_pct)],
    ["Endkapital",     geld(k.endkapital),            ""],
    ["Trades",         k.n_trades,                    ""],
    ["Trefferquote",   pct(k.trefferquote_pct, 1),    ""],
    ["Mittel je Trade",pct(k.mittel_pct, 3),          farbe(k.mittel_pct)],
    ["Median je Trade",pct(k.median_pct, 3),          farbe(k.median_pct)],
    ["max. R&uuml;ckgang",  pct(k.max_drawdown_pct, 1),    "schlecht"],
    ["Profitfaktor",   nz(k.profit_faktor, 2),        ""],
    ["t-Wert",         nz(k.t_wert, 2),               ueber ? "gut" : "warnfarbe"],
    ["Schwelle",       nz(n.schwelle, 2),             ""],
    ["Handelstage",    k.n_handelstage ?? "–",        ""],
    ["Signale",        (k.n_signale ?? 0).toLocaleString("de-DE"), ""],
  ];
  $("#kennzahlen").innerHTML = kacheln.map(([name, wert, kl]) =>
    `<div class="kachel"><span class="k-wert ${kl}">${wert}</span>
     <span class="k-name">${name}</span></div>`).join("");

  const urteil = ueber
    ? `Der t-Wert liegt &uuml;ber der Zufallsschwelle. Das ist noch kein Befund &ndash;
       ein Historienlauf darf verwerfen, nie abnehmen. Der n&auml;chste Schritt w&auml;re
       ein Flottenbot im Vorw&auml;rtsschatten, keine Live-Schaltung.`
    : `Der t-Wert liegt <b>unter</b> der Zufallsschwelle von ${nz(n.schwelle,2)}.
       Bei ${n.n_versuche} Versuchen ist das der Normalfall, kein Befund.`;

  $("#hinweise").innerHTML =
    `<div class="hinweiskarte">${urteil}</div>` +
    n.hinweise.map(h => `<div class="hinweiskarte">${h}</div>`).join("");
  $("#ergebnisblock").hidden = false;
  LETZTER_LAUF = n.lauf_id;
}

/* ---------- Tabellen ---------- */
function tabelle(daten, spalten) {
  if (!daten.length) return `<p class="mini">Keine Daten.</p>`;
  const kopf = spalten.map(([, t]) => `<th>${t}</th>`).join("");
  const zeilen = daten.map(r => "<tr>" + spalten.map(([k, , fmt]) => {
    const v = r[k];
    const txt = fmt ? fmt(v) : (v ?? "–");
    const kl = (typeof v === "number" && /pct|usd/.test(k)) ? farbe(v) : "";
    return `<td class="${kl}">${txt}</td>`;
  }).join("") + "</tr>").join("");
  return `<div class="tabellenrahmen"><table><thead><tr>${kopf}</tr></thead>
          <tbody>${zeilen}</tbody></table></div>`;
}

async function tabsNeu() {
  const q = LETZTER_LAUF ? `?lauf=${LETZTER_LAUF}` : "";

  const besten = await (await fetch("/api/besten" + q)).json();
  $("#tab-besten").innerHTML =
    `<p class="mini">Nach Gesamtgewinn. <b>Vorsicht:</b> Bei hunderten Symbolen
     steht hier immer etwas Beeindruckendes &ndash; auch wenn die Strategie nichts
     kann. Erst mehrere L&auml;ufe zeigen, ob dieselben Namen wiederkehren.</p>` +
    tabelle(besten, [
      ["symbol", "Symbol"], ["n_trades", "Trades"],
      ["summe_usd", "Gewinn $", v => nz(v, 0)],
      ["mittel_pct", "Mittel", v => pct(v, 2)],
      ["treffer_pct", "Treffer", v => pct(v, 0)],
      ["bester_pct", "bester", v => pct(v, 1)],
      ["schlechtester_pct", "schlecht.", v => pct(v, 1)],
    ]);

  const trades = await (await fetch("/api/trades" + q)).json();
  $("#tab-trades").innerHTML = tabelle(trades.slice(-300).reverse(), [
    ["symbol", "Symbol"],
    ["einstieg_ts", "Einstieg", v => (v || "").slice(0, 16).replace("T", " ")],
    ["ausloeser_anstieg_pct", "Ausl&ouml;ser", v => pct(v, 1)],
    ["rel_volumen", "Vol x", v => nz(v, 1)],
    ["gehalten_bars", "Bars"],
    ["grund", "Ausstieg"],
    ["rendite_pct", "Rendite", v => pct(v, 2)],
    ["gewinn_usd", "$", v => nz(v, 0)],
  ]);

  const laeufe = await (await fetch("/api/laeufe")).json();
  $("#tab-laeufe").innerHTML =
    `<p class="mini">Jeder Lauf z&auml;hlt dauerhaft mit &ndash; auch verworfene.
     Das ist Absicht: Ein Z&auml;hler, aus dem man Versuche entfernen kann,
     senkt nachtr&auml;glich die H&uuml;rde, gegen die er messen soll.</p>` +
    tabelle(laeufe, [
      ["gestartet_am", "Start", v => (v || "").slice(0, 16).replace("T", " ")],
      ["notiz", "Notiz"],
      ["n_symbole", "Symbole"],
      ["n_trades", "Trades"],
      ["rendite_pct", "Rendite", v => pct(v, 1)],
      ["trefferquote_pct", "Treffer", v => pct(v, 0)],
      ["t_wert", "t", v => nz(v, 2)],
      ["max_drawdown_pct", "max. R&uuml;ckgang", v => pct(v, 1)],
      ["status", "Status"],
    ]);
}

/* ---------- Bedienung ---------- */
function laufModus(an) {
  LAEUFT = an;
  $("#btn-start").disabled = an;
  $("#btn-daten").disabled = an;
  $("#btn-stop").disabled = !an;
}

async function standHolen() {
  const jahr = $("#jahr").value, raster = $("#raster").value;
  const s = await (await fetch(`/api/stand?jahr=${jahr}&raster=${raster}`)).json();
  $("#k-versuche").textContent = s.n_versuche;
  $("#k-schwelle").textContent = nz(s.schwelle, 2);
  $("#k-vorrat").textContent = s.vorrat.symbole;
  $("#vorrat-stand").innerHTML = s.vorrat.symbole
    ? `Vorrat: <b>${s.vorrat.symbole} Symbole</b>, ${nz(s.vorrat.mb, 0)} MB.`
    : `<b>Noch kein Vorrat f&uuml;r ${jahr}/${raster}.</b> Erst laden, dann testen.`;
  if (!FELDER.length) felderBauen(s.felder, s.vorgaben);
  laufModus(s.aktiv);
}

$("#btn-daten").addEventListener("click", async () => {
  const koerper = {
    n_symbole: Number($("#n_symbole").value),
    jahr: Number($("#jahr").value),
    raster: $("#raster").value,
  };
  log(`Kursdaten anfordern: ${koerper.n_symbole} Symbole, ${koerper.jahr}, ${koerper.raster}`);
  const a = await (await fetch("/api/daten", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(koerper),
  })).json();
  if (a.gestartet) laufModus(true); else log("Es l&auml;uft bereits etwas.", "warn");
});

$("#btn-start").addEventListener("click", async () => {
  const koerper = {
    config: configLesen(),
    jahr: Number($("#jahr").value),
    raster: $("#raster").value,
    notiz: $("#notiz").value,
    max_symbole: $("#max_symbole").value ? Number($("#max_symbole").value) : null,
  };
  $("#log").innerHTML = "";
  const a = await (await fetch("/api/lauf", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(koerper),
  })).json();
  if (a.gestartet) laufModus(true);
  else log(a.fehler || "Es l&auml;uft bereits etwas.", "fehler");
});

$("#btn-stop").addEventListener("click", () =>
  fetch("/api/stop", { method: "POST" }));

$$(".chip").forEach(b => b.addEventListener("click", () => {
  $("#f-fenster_bars").value = b.dataset.bars;
  vorschau();
}));

$$(".reiter-knopf").forEach(b => b.addEventListener("click", () => {
  $$(".reiter-knopf").forEach(x => x.classList.remove("aktiv"));
  b.classList.add("aktiv");
  $$(".tab").forEach(t => t.hidden = (t.id !== b.dataset.ziel));
}));

["jahr", "raster"].forEach(id => $("#" + id).addEventListener("change", standHolen));

standHolen();
stromVerbinden();
tabsNeu();
log("Werkstatt bereit. Ohne Kursdaten geht nichts – Schritt 1 zuerst.", "info");
