/* Interactive explainers of the YSimulator documentation. Vanilla JavaScript, no dependencies, nothing is sent anywhere.
   Usage: <div class="ys-lab" data-lab="pricing"></div>. The language is the one of <html lang>.
   The formulas are the ones of the runtime (YSimulator/YClient and YServer);
   the pages say where a widget simplifies. */
(function () {
  'use strict';
  var doc = document;
  var IT = (doc.documentElement.getAttribute('lang') || 'en') === 'it';

  /* ---------- tiny helpers ---------- */
  function h(tag, attrs, kids) {
    var e = doc.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'class') e.className = attrs[k];
      else if (k === 'text') e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) { if (c != null) e.appendChild(typeof c === 'string' ? doc.createTextNode(c) : c); });
    return e;
  }
  function t(en, it) { return IT ? it : en; }
  function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }
  function pyRound(x) { var f = Math.floor(x), d = x - f; if (d > 0.5) return f + 1; if (d < 0.5) return f; return f % 2 === 0 ? f : f + 1; }
  function halfUp(x) { return Math.floor(x + 0.5); }
  function pct(x) { return Math.round(x * 1000) / 10 + '%'; }
  function num(x) { return String(Math.round(x * 100) / 100); }
  function rng(seed) { var a = seed >>> 0; return function () { a += 0x6D2B79F5; var r = Math.imul(a ^ a >>> 15, 1 | a); r ^= r + Math.imul(r ^ r >>> 7, 61 | r); return ((r ^ r >>> 14) >>> 0) / 4294967296; }; }
  function normal(r) { var u = 0, v = 0; while (u === 0) u = r(); while (v === 0) v = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }

  function slider(label, min, max, step, val, fmt, on) {
    var out = h('output', { text: fmt ? fmt(val) : String(val) });
    var inp = h('input', { type: 'range', min: min, max: max, step: step, value: val });
    inp.addEventListener('input', function () { var v = parseFloat(inp.value); out.textContent = fmt ? fmt(v) : String(v); on(v); });
    var el = h('label', {}, [h('b', {}, [h('span', { text: label }), out]), inp]);
    el.set = function (v) { inp.value = v; out.textContent = fmt ? fmt(v) : String(v); };
    return el;
  }
  function select(label, options, val, on) {
    var s = h('select');
    options.forEach(function (o) { var op = h('option', { value: o[0], text: o[1] }); if (o[0] === val) op.selected = true; s.appendChild(op); });
    s.addEventListener('change', function () { on(s.value); });
    return h('label', {}, [h('b', {}, [h('span', { text: label })]), s]);
  }
  function seg(label, options, val, on) {
    var box = h('div', { class: 'ys-seg', role: 'group', 'aria-label': label }), btns = [];
    options.forEach(function (o) {
      var b = h('button', { type: 'button', text: o[1], 'aria-pressed': o[0] === val ? 'true' : 'false' });
      b.addEventListener('click', function () { btns.forEach(function (x) { x.setAttribute('aria-pressed', 'false'); }); b.setAttribute('aria-pressed', 'true'); on(o[0]); });
      btns.push(b); box.appendChild(b);
    });
    return h('label', {}, [h('b', {}, [h('span', { text: label })]), box]);
  }
  function check(label, val, on) {
    var c = h('input', { type: 'checkbox' }); c.checked = !!val;
    c.addEventListener('change', function () { on(c.checked); });
    return h('label', { class: 'ys-chk' }, [c, h('span', { text: label })]);
  }
  function kpi(label, value, cls) { return h('div', { class: 'ys-kpi' + (cls ? ' ' + cls : '') }, [h('small', { text: label }), h('b', { text: String(value) })]); }
  function msg(text, cls) { return h('div', { class: 'ys-msg' + (cls ? ' is-' + cls : ''), text: text }); }
  function bars(rows, max) {
    var m = max || Math.max.apply(null, rows.map(function (r) { return r[1]; }).concat([1e-9]));
    return h('div', { class: 'ys-bars' }, rows.map(function (r) {
      var i = h('i'); i.style.width = clamp(r[1] / m * 100, 0, 100) + '%';
      return h('div', { class: 'ys-bar' }, [h('span', { text: r[0] }), h('div', {}, [i]), h('em', { text: r[2] != null ? r[2] : num(r[1]) })]);
    }));
  }
  function table(head, rows) {
    return h('table', { class: 'ys-table-mini' }, [
      h('thead', {}, [h('tr', {}, head.map(function (x) { return h('th', { text: x }); }))]),
      h('tbody', {}, rows.map(function (r) { return h('tr', {}, r.map(function (x) { return h('td', { text: String(x) }); })); }))
    ]);
  }
  function svg(w, hgt) { var s = doc.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('viewBox', '0 0 ' + w + ' ' + hgt); s.setAttribute('class', 'ys-plot'); s.setAttribute('role', 'img'); return s; }
  function sv(s, tag, attrs, text) { var e = doc.createElementNS('http://www.w3.org/2000/svg', tag); Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); }); if (text != null) e.textContent = text; s.appendChild(e); return e; }
  function shell(host, title, controls, out) {
    host.textContent = '';
    host.appendChild(h('div', { class: 'ys-lab-head' }, [h('p', { class: 'ys-lab-title', text: title }), h('span', { class: 'ys-lab-hint', text: t('Move the controls; everything is computed in your browser.', 'Muovi i controlli; tutto è calcolato nel tuo browser.') })]));
    host.appendChild(h('div', { class: 'ys-lab-body' }, [h('div', { class: 'ys-ctl' }, controls), out]));
  }

  var LABS = {};
  /* ---------- barrier: dynamic barrier with heartbeats ---------- */
  LABS.barrier = function (host) {
    var S = { n: 3, d1: 4, d2: 6, d3: 9, to: 20, crash: false, at: 30 }, out = h('div', { class: 'ys-out' });
    function run() {
      var dur = [S.d1, S.d2, S.d3].slice(0, S.n), T = 120, tcur = 0, slots = 0, rows = [], stall = 0, active = dur.map(function () { return true; });
      var crashedAt = S.crash && S.n > 1 ? S.at : Infinity;
      while (tcur < T) {
        var fin = 0, wait = 0;
        dur.forEach(function (d, i) {
          if (!active[i]) return;
          if (i === 1 && tcur + d > crashedAt) { // client 2 stops sending heartbeats at crashedAt: the server waits for the timeout, then drops it
            var drop = Math.max(tcur, crashedAt) + S.to; active[i] = false; wait = Math.max(wait, drop - tcur); return;
          }
          fin = Math.max(fin, d);
        });
        var step = Math.max(fin, wait); if (step <= 0) break;
        if (wait > fin) stall += wait - fin;
        if (tcur + step > T) break;
        tcur += step; slots++; if (rows.length < 30) rows.push([slots, Math.round(tcur), Math.round(step)]);
      }
      return { slots: slots, stall: Math.round(stall), alive: active.filter(Boolean).length, rows: rows };
    }
    function draw() {
      out.textContent = '';
      var r = run(), best = Math.max(S.d1, S.n > 1 ? S.d2 : 0, S.n > 2 ? S.d3 : 0);
      var s = svg(480, 120), max = 120;
      for (var i = 0; i < S.n; i++) {
        var d = [S.d1, S.d2, S.d3][i];
        for (var x = 0; x < max; x += best) { var w = Math.min(d, best, max - x); sv(s, 'rect', { x: 20 + x / max * 440, y: 14 + i * 30, width: Math.max(w / max * 440 - 1, 1), height: 18, rx: 3, fill: 'var(--accent)', opacity: 0.8 }); }
        sv(s, 'text', { x: 4, y: 27 + i * 30, 'font-size': 9, fill: 'var(--muted)' }, 'c' + (i + 1));
      }
      if (S.crash && S.n > 1) sv(s, 'line', { x1: 20 + S.at / max * 440, x2: 20 + S.at / max * 440, y1: 6, y2: 104, stroke: 'var(--danger)', 'stroke-dasharray': '4 3' });
      out.appendChild(s);
      out.appendChild(h('div', { class: 'ys-kpis' }, [kpi(t('Slots finished in 120 s', 'Slot completati in 120 s'), r.slots), kpi(t('Slot length', 'Durata di uno slot'), best + ' s'), kpi(t('Clients still in the barrier', 'Client ancora nella barriera'), r.alive + '/' + S.n, r.alive < S.n ? 'is-bad' : 'is-ok')]));
      out.appendChild(msg(S.crash && S.n > 1 ? t('Client 2 goes silent at second ' + S.at + ': the others wait for timeout_seconds (' + S.to + ' s), then the server drops it and the run goes on without stalling forever.', 'Il client 2 tace al secondo ' + S.at + ': gli altri aspettano timeout_seconds (' + S.to + ' s), poi il server lo toglie e la run prosegue senza bloccarsi per sempre.') : t('A slot ends only when every active client has submitted its actions, so the slowest client sets the pace.', 'Uno slot termina solo quando ogni client attivo ha inviato le sue azioni: il client più lento detta il ritmo.'), S.crash ? 'warn' : ''));
      out.appendChild(h('p', { class: 'ys-lab-hint', text: t('Simplified: constant time per slot for each client; the real server also polls with WAIT and PROCEED answers.', 'Semplificato: tempo costante per slot per ogni client; il server reale risponde anche con WAIT e PROCEED a ogni richiesta.') }));
    }
    shell(host, t('The barrier of the server', 'La barriera del server'), [
      slider(t('Clients', 'Client'), 1, 3, 1, 3, null, function (v) { S.n = v; draw(); }),
      slider(t('Client 1: seconds per slot', 'Client 1: secondi per slot'), 1, 20, 1, 4, null, function (v) { S.d1 = v; draw(); }),
      slider(t('Client 2: seconds per slot', 'Client 2: secondi per slot'), 1, 20, 1, 6, null, function (v) { S.d2 = v; draw(); }),
      slider(t('Client 3: seconds per slot', 'Client 3: secondi per slot'), 1, 20, 1, 9, null, function (v) { S.d3 = v; draw(); }),
      slider('timeout_seconds', 5, 60, 5, 20, null, function (v) { S.to = v; draw(); }),
      check(t('Client 2 crashes at second 30', 'Il client 2 va in crash al secondo 30'), false, function (v) { S.crash = v; draw(); })
    ], out);
    draw();
  };


  /* ---------- actions: archetype-limited action draw ---------- */
  LABS.actions = function (host) {
    var W = { post: 3, comment: 5, read: 2, share: 1, search: 5, follow: 0.1 };
    var ARCH = { none: null, validator: ['share', 'read'], broadcaster: ['post', 'share', 'comment'], explorer: ['search', 'follow'] };
    var S = { arch: 'none', page: false, seed: 4, wPost: 3, wCom: 5, wRead: 2, wSearch: 5 }, out = h('div', { class: 'ys-out' });
    function draw() {
      out.textContent = '';
      W.post = S.wPost; W.comment = S.wCom; W.read = S.wRead; W.search = S.wSearch;
      var keys = S.page ? ['share_link'] : Object.keys(W).filter(function (k) { return !ARCH[S.arch] || ARCH[S.arch].indexOf(k) >= 0; });
      var w = {}; keys.forEach(function (k) { w[k] = S.page ? 1 : W[k]; });
      var tot = keys.reduce(function (a, k) { return a + w[k]; }, 0) || 1, r = rng(S.seed), seq = [];
      for (var i = 0; i < 20; i++) { var v = r() * tot, c = 0, a = keys[keys.length - 1]; for (var j = 0; j < keys.length; j++) { c += w[keys[j]]; if (v < c) { a = keys[j]; break; } } seq.push(a); }
      out.appendChild(bars(keys.map(function (k) { return [k, w[k] / tot, pct(w[k] / tot)]; }), 1));
      out.appendChild(h('p', { class: 'ys-lab-hint', text: t('Twenty draws in a row: ', 'Venti estrazioni di fila: ') + seq.join(' · ') }));
      out.appendChild(h('p', { class: 'ys-lab-hint', text: t('Weights are relative (they need not sum to 1). An archetype removes the actions it does not have; a page agent can only share links and attempts at most one action per slot. Image and news weights are 0 in the example.', 'I pesi sono relativi (non devono sommare a 1). Un archetipo toglie le azioni che non ha; un agente pagina può solo condividere link e tenta al massimo un’azione per slot. I pesi di immagini e notizie sono 0 nell’esempio.') }));
    }
    var again = h('button', { type: 'button', class: 'ys-btn ghost', text: t('Draw again', 'Estrai ancora') });
    again.addEventListener('click', function () { S.seed = (S.seed * 7919 + 11) % 100003; draw(); });
    shell(host, t('What an agent picks next', 'Che cosa sceglie un agente'), [
      select(t('archetype', 'archetype'), [['none', t('(none)', '(nessuno)')], ['validator', 'validator'], ['broadcaster', 'broadcaster'], ['explorer', 'explorer']], 'none', function (v) { S.arch = v; draw(); }),
      check(t('Page agent (is_page)', 'Agente pagina (is_page)'), false, function (v) { S.page = v; draw(); }),
      slider('post', 0, 10, 0.5, 3, null, function (v) { S.wPost = v; draw(); }),
      slider('comment', 0, 10, 0.5, 5, null, function (v) { S.wCom = v; draw(); }),
      slider('read', 0, 10, 0.5, 2, null, function (v) { S.wRead = v; draw(); }),
      slider('search', 0, 10, 0.5, 5, null, function (v) { S.wSearch = v; draw(); }),
      h('div', { class: 'ys-btnrow' }, [again])
    ], out);
    draw();
  };


  /* ---------- recsys: content recommender modes ---------- */
  LABS.recsys = function (host) {
    var S = { mode: 'ReverseChronoFollowersPopularity', n: 8, ratio: 0.6, vis: 36, seed: 2 }, out = h('div', { class: 'ys-out' });
    var posts = (function () { var r = rng(11), a = []; for (var i = 0; i < 40; i++) a.push({ id: 'p' + (i + 1), age: Math.floor(r() * 60), likes: Math.floor(Math.pow(r(), 3) * 30), fol: r() < 0.3 }); return a; })();
    function pick() {
      var vis = posts.filter(function (p) { return p.age <= S.vis; }), r = rng(S.seed);
      var byTime = function (a, b) { return a.age - b.age; };
      var byTimePop = function (a, b) { return a.age - b.age || b.likes - a.likes; };
      var res;
      if (S.mode === 'random') { var c = vis.slice(); res = []; while (res.length < S.n && c.length) res.push(c.splice(Math.floor(r() * c.length), 1)[0]); return res; }
      if (S.mode === 'ReverseChrono') return vis.slice().sort(byTime).slice(0, S.n);
      if (S.mode === 'ReverseChronoPopularity') return vis.slice().sort(byTimePop).slice(0, S.n);
      var f = vis.filter(function (p) { return p.fol; }), o = vis.filter(function (p) { return !p.fol; });
      var cmp = S.mode === 'ReverseChronoFollowers' ? byTime : byTimePop;
      var nf = Math.round(S.n * S.ratio);
      res = f.sort(cmp).slice(0, nf); res = res.concat(o.sort(cmp).slice(0, S.n - res.length));
      if (res.length < S.n) res = res.concat(f.sort(cmp).slice(res.length, S.n));
      return res.slice(0, S.n);
    }
    function draw() {
      out.textContent = '';
      var res = pick(), fol = res.filter(function (p) { return p.fol; }).length, age = res.length ? res.reduce(function (a, p) { return a + p.age; }, 0) / res.length : 0, lk = res.length ? res.reduce(function (a, p) { return a + p.likes; }, 0) / res.length : 0;
      out.appendChild(table([t('Post', 'Post'), t('Age (slots)', 'Età (slot)'), t('Reactions', 'Reazioni'), t('From a followed user', 'Da un utente seguito')], res.map(function (p) { return [p.id, p.age, p.likes, p.fol ? '●' : '']; })));
      out.appendChild(h('div', { class: 'ys-kpis' }, [kpi(t('Posts shown', 'Post mostrati'), res.length), kpi(t('From followed users', 'Da utenti seguiti'), fol + '/' + res.length), kpi(t('Mean age', 'Età media'), num(age)), kpi(t('Mean reactions', 'Reazioni medie'), num(lk))]));
      out.appendChild(h('p', { class: 'ys-lab-hint', text: t('40 synthetic posts, 30% from accounts the reader follows. Simplified: the followers modes fill a share followers_ratio of the page from followed users, each part newest first (with reactions as tie-break in the Popularity modes); the runtime applies the same idea in SQL or Redis.', '40 post sintetici, il 30% da account seguiti dal lettore. Semplificato: le modalità con follower riempiono una quota followers_ratio della pagina con utenti seguiti, ciascuna parte dal più recente (con le reazioni come spareggio nelle modalità Popularity); il runtime applica la stessa idea in SQL o Redis.') }));
    }
    shell(host, t('One feed, five recommenders', 'Un feed, cinque raccomandatori'), [
      select('recsys.content', [['random', 'random'], ['ReverseChrono', 'ReverseChrono'], ['ReverseChronoPopularity', 'ReverseChronoPopularity'], ['ReverseChronoFollowers', 'ReverseChronoFollowers'], ['ReverseChronoFollowersPopularity', 'ReverseChronoFollowersPopularity']], S.mode, function (v) { S.mode = v; draw(); }),
      slider('n_posts', 3, 15, 1, 8, null, function (v) { S.n = v; draw(); }),
      slider('followers_ratio', 0, 1, 0.1, 0.6, num, function (v) { S.ratio = v; draw(); }),
      slider('visibility_rounds', 6, 60, 6, 36, null, function (v) { S.vis = v; draw(); })
    ], out);
    draw();
  };


  /* ---------- decay: follow_action_decay ---------- */
  LABS.decay = function (host) {
    var S = { fn: 'exponential', half: 168, rate: 0.01, min: 0.1, w: 0.1 }, out = h('div', { class: 'ys-out' });
    function m(r) { var v = S.fn === 'exponential' ? Math.pow(0.5, r / S.half) : 1 - S.rate * r; return Math.max(S.min, Math.min(1, v)); }
    function draw() {
      out.textContent = '';
      var s = svg(480, 150), R = 480, pts = [];
      for (var x = 0; x <= R; x += 8) pts.push((14 + x / R * 450) + ',' + (120 - m(x) * 100));
      sv(s, 'polyline', { points: pts.join(' '), fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2.5 });
      sv(s, 'line', { x1: 14, x2: 464, y1: 120 - S.min * 100, y2: 120 - S.min * 100, stroke: 'var(--muted)', 'stroke-dasharray': '3 3' });
      [0, 120, 240, 360, 480].forEach(function (v) { sv(s, 'text', { x: 14 + v / R * 450, y: 138, 'text-anchor': 'middle', 'font-size': 9, fill: 'var(--muted)' }, String(v)); });
      out.appendChild(s);
      out.appendChild(h('div', { class: 'ys-kpis' }, [kpi(t('After 1 day (24 rounds)', 'Dopo 1 giorno (24 turni)'), pct(m(24))), kpi(t('After 7 days', 'Dopo 7 giorni'), pct(m(168))), kpi(t('After 14 days', 'Dopo 14 giorni'), pct(m(336))), kpi(t('Weight of FOLLOW after 14 days', 'Peso di FOLLOW dopo 14 giorni'), num(S.w * m(336)))]));
      out.appendChild(h('p', { class: 'ys-lab-hint', text: t('The multiplier scales the weight of the follow action for an agent according to the rounds since it joined, and never falls under min_probability_ratio. Exponential: 0.5^(rounds / half_life); linear: 1 − decay_rate × rounds.', 'Il moltiplicatore scala il peso dell’azione follow di un agente in base ai turni dal suo ingresso e non scende mai sotto min_probability_ratio. Esponenziale: 0,5^(turni / emivita); lineare: 1 − decay_rate × turni.') }));
    }
    shell(host, t('Follows that fade with age', 'Follow che si spengono con l’età'), [
      seg('decay_function', [['exponential', 'exponential'], ['linear', 'linear']], 'exponential', function (v) { S.fn = v; draw(); }),
      slider('half_life_rounds', 24, 336, 24, 168, null, function (v) { S.half = v; draw(); }),
      slider('decay_rate', 0.001, 0.03, 0.001, 0.01, num, function (v) { S.rate = v; draw(); }),
      slider('min_probability_ratio', 0, 0.5, 0.05, 0.1, num, function (v) { S.min = v; draw(); }),
      slider(t('weight of follow', 'peso di follow'), 0.05, 1, 0.05, 0.1, num, function (v) { S.w = v; draw(); })
    ], out);
    draw();
  };


  /* ---------- churn: population size over days ---------- */
  LABS.churn = function (host) {
    var S = { n0: 100, cp: 0.1, cpct: 0.05, inact: 0.3, np: 0.1, npct: 0.05, ch: true, nw: true, days: 30 }, out = h('div', { class: 'ys-out' });
    function draw() {
      out.textContent = '';
      var pop = S.n0, ser = [pop], gone = 0, born = 0;
      for (var d = 1; d <= S.days; d++) {
        var l = S.ch ? S.cp * S.cpct * pop * S.inact : 0, a = S.nw ? S.np * S.npct * pop : 0;
        pop = Math.max(pop - l + a, 0); gone += l; born += a; ser.push(pop);
      }
      var mx = Math.max.apply(null, ser.concat([S.n0])) * 1.1, s = svg(480, 150);
      var pts = ser.map(function (v, i) { return (14 + i / S.days * 450) + ',' + (125 - v / mx * 105); });
      sv(s, 'polyline', { points: pts.join(' '), fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2.5 });
      sv(s, 'line', { x1: 14, x2: 464, y1: 125 - S.n0 / mx * 105, y2: 125 - S.n0 / mx * 105, stroke: 'var(--muted)', 'stroke-dasharray': '3 3' });
      [0, 10, 20, 30].forEach(function (v) { if (v <= S.days) sv(s, 'text', { x: 14 + v / S.days * 450, y: 142, 'text-anchor': 'middle', 'font-size': 9, fill: 'var(--muted)' }, String(v)); });
      out.appendChild(s);
      out.appendChild(h('div', { class: 'ys-kpis' }, [kpi(t('Population at the end', 'Popolazione alla fine'), Math.round(pop)), kpi(t('Left (expected)', 'Usciti (attesi)'), Math.round(gone), 'is-bad'), kpi(t('Joined (expected)', 'Entrati (attesi)'), Math.round(born), 'is-ok')]));
      out.appendChild(h('p', { class: 'ys-lab-hint', text: t('Expected values, day by day: each day the churn check runs with probability churn_probability and removes churn_percentage of the inactive agents (here a share of the population is inactive); new agents arrive with probability probability_new_agents, as percentage_new_agents of the population. The runtime draws the real numbers at random.', 'Valori attesi, giorno per giorno: ogni giorno il controllo di abbandono scatta con probabilità churn_probability e rimuove churn_percentage degli agenti inattivi (qui una quota della popolazione è inattiva); i nuovi agenti arrivano con probabilità probability_new_agents, in misura di percentage_new_agents della popolazione. Il runtime estrae i numeri reali a caso.') }));
    }
    shell(host, t('A population that changes', 'Una popolazione che cambia'), [
      slider(t('initial agents', 'agenti iniziali'), 20, 500, 10, 100, null, function (v) { S.n0 = v; draw(); }),
      check('churn.enabled', true, function (v) { S.ch = v; draw(); }),
      slider('churn_probability', 0, 1, 0.05, 0.1, num, function (v) { S.cp = v; draw(); }),
      slider('churn_percentage', 0, 1, 0.05, 0.05, num, function (v) { S.cpct = v; draw(); }),
      slider(t('share of inactive agents', 'quota di agenti inattivi'), 0, 1, 0.05, 0.3, num, function (v) { S.inact = v; draw(); }),
      check('new_agents.enabled', true, function (v) { S.nw = v; draw(); }),
      slider('probability_new_agents', 0, 1, 0.05, 0.1, num, function (v) { S.np = v; draw(); }),
      slider('percentage_new_agents', 0, 0.5, 0.01, 0.05, num, function (v) { S.npct = v; draw(); })
    ], out);
    draw();
  };


  LABS.opinions = function (host) {
    var S = { eps: 0.25, mu: 0.5, theta: 0, n: 60, step: 0, timer: null, ops: [], seed: 4 }, out = h('div', { class: 'ys-out' }), rnd;
    function reset() { stop(); rnd = rng(S.seed); S.ops = []; for (var i = 0; i < S.n; i++) S.ops.push(rnd()); S.step = 0; draw(); }
    function stop() { if (S.timer) { clearInterval(S.timer); S.timer = null; } }
    function bc(x, y) { if (Math.abs(y - x) > S.eps) { if (S.theta) return x > y ? Math.min(x + S.theta, 1) : Math.max(x - S.theta, 0); return x; } return x + S.mu * (y - x); }
    function tick(k) { for (var q = 0; q < k; q++) { var i = Math.floor(rnd() * S.n), j = Math.floor(rnd() * S.n); if (i === j) continue; S.ops[i] = bc(S.ops[i], S.ops[j]); S.step++; } }
    function draw() {
      out.textContent = '';
      var B = 20, h2 = []; for (var b = 0; b < B; b++) h2.push(0);
      S.ops.forEach(function (v) { h2[Math.min(B - 1, Math.floor(v * B))]++; });
      var s = svg(480, 140), m = Math.max.apply(null, h2.concat([1]));
      h2.forEach(function (c, k) { sv(s, 'rect', { x: 12 + k * 22.8, y: 118 - c / m * 100, width: 20, height: c / m * 100, rx: 3, fill: 'var(--accent)', opacity: 0.85 }); });
      [0, 0.5, 1].forEach(function (v) { sv(s, 'text', { x: 12 + v * 456, y: 134, 'text-anchor': v === 0 ? 'start' : v === 1 ? 'end' : 'middle', 'font-size': 9, fill: 'var(--muted)' }, String(v)); });
      out.appendChild(s);
      var sorted = S.ops.slice().sort(function (a, b) { return a - b; }), clusters = 1; for (var i = 1; i < sorted.length; i++) if (sorted[i] - sorted[i - 1] > 0.05) clusters++;
      var mean = S.ops.reduce(function (a, b) { return a + b; }, 0) / S.n, sd = Math.sqrt(S.ops.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / S.n);
      out.appendChild(h('div', { class: 'ys-kpis' }, [kpi(t('Interactions', 'Interazioni'), S.step), kpi(t('Clusters (gap > 0.05)', 'Gruppi (distanza > 0,05)'), clusters), kpi(t('Spread (std)', 'Dispersione (dev. std)'), num(sd))]));
      out.appendChild(h('p', { class: 'ys-lab-hint', text: t('Each interaction is one agent (reader) reading another (author) on a topic. If their opinions are within epsilon the reader moves a fraction mu towards the author; otherwise it stays, or, if theta is not 0, steps away from the author by theta (clamped to [0, 1]). Same rule as the bounded_confidence model; in a run the topic of a message decides who interacts.', 'Ogni interazione è un agente (lettore) che legge un altro (autore) su un argomento. Se le loro opinioni distano meno di epsilon il lettore si sposta di una frazione mu verso l’autore; altrimenti resta fermo oppure, se theta non è 0, si allontana dall’autore di theta (limitato a [0, 1]). Stessa regola del modello bounded_confidence; in una run è l’argomento del messaggio a decidere chi interagisce.') }));
    }
    var play = h('button', { type: 'button', class: 'ys-btn', text: t('▶ Play', '▶ Avvia') });
    play.addEventListener('click', function () { if (S.timer) { stop(); return; } S.timer = setInterval(function () { tick(30); draw(); if (S.step > 6000) stop(); }, 80); });
    var one = h('button', { type: 'button', class: 'ys-btn ghost', text: t('+100 interactions', '+100 interazioni') });
    one.addEventListener('click', function () { stop(); tick(100); draw(); });
    var rs = h('button', { type: 'button', class: 'ys-btn ghost', text: t('Reset', 'Azzera') });
    rs.addEventListener('click', reset);
    shell(host, t('Opinions that attract (and repel)', 'Opinioni che si attraggono (e si respingono)'), [
      slider('epsilon', 0.05, 0.6, 0.01, 0.25, num, function (v) { S.eps = v; }),
      slider('mu', 0.05, 0.5, 0.01, 0.5, num, function (v) { S.mu = v; }),
      slider('theta', 0, 0.1, 0.005, 0, num, function (v) { S.theta = v; }),
      h('div', { class: 'ys-btnrow' }, [play, one, rs])
    ], out);
    reset();
  };


  /* ---------- boot ---------- */
  function boot() {
    Array.prototype.forEach.call(doc.querySelectorAll('.ys-lab[data-lab]'), function (el) {
      var f = LABS[el.getAttribute('data-lab')];
      if (!f) return;
      try { f(el); } catch (e) { el.textContent = 'Interactive explainer unavailable.'; if (window.console) console.error(e); }
    });
  }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot); else boot();
})();

