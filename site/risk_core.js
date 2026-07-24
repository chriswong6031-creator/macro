/* risk_core.js — the pure book-structure math behind the Watchlist Risk
   Intelligence surface. No DOM, no fetch, no globals beyond window.RiskCore.

   "You think you own 8 trades; you mostly own one." Given the nightly
   orthogonalized 9-factor model (factor_betas.json: per-ticker marginal betas
   b_i, near-diagonal factor covariance F, per-name idiosyncratic vol σ_ε,i) and
   a weights map {ticker -> dollarValue}, this computes the institutionally-honest
   book-structure reads (masterplan §7):

     - book factor beta vector  β_book = Σ_i w_i b_i
     - book variance            V = β'Fβ + Σ_i w_i² σ²_ε,i          (annualized)
     - factor variance shares   s_k = β_k (Fβ)_k / V  (Euler; tiny negatives
                                clamped, clamped mass disclosed if > 2%)
     - effective number of bets ENB = 1 / Σ_j s_j²  over {9 factor buckets +
                                n PER-NAME idio buckets} — idio is NEVER lumped
     - pairwise implied corr    ρ_ij = b_i'F b_j / (σ_i σ_j)
     - twin clusters            connected components at ρ ≥ 0.70
     - per-position risk        MCTR share_i = w_i (Σ w)_i / V  (can be negative
                                = hedge; Σ = B F B' + D restricted to the book)
     - stress lens              identical math under factor_cov_stress (idio held
                                v1-invariant); available only when the emit carries
                                the stress block AND stress_meta.available !== false
     - coverage split           modeled vs unmodeled dollars; abstain > 40% unmodeled

   This is a faithful superset of engine.factor_exposure.portfolio_exposure()
   (the FX panel's aggregate()): the factor-share arithmetic is the same B F B' + D
   decomposition, extended with the per-name idio buckets, pairwise corr, twins and
   the stress lens. Measurement, not a forecast — display-tier only (WRI-R8); no
   fused composite anywhere (WRI-R2). Runs in the browser and under node (tests).

   Depends on nothing. Attaches window.RiskCore (browser) / module.exports (node). */
(function (root) {
  'use strict';

  var TWIN_RHO = 0.70;          // twin-cluster threshold (masterplan §7)
  var ABSTAIN_UNMODELED = 0.40; // > 40% of book dollars unmodeled -> verdict abstains
  var CLAMP_DISCLOSE = 0.02;    // disclose when clamped negative mass > 2% of |shares|

  // ---- tiny helpers -------------------------------------------------------
  function isNum(x) { return typeof x === 'number' && isFinite(x); }
  function factorKeys(data) {
    return (data.factors || []).map(function (f) { return f.key; });
  }

  // Normalize a raw {ticker -> dollarValue|weight} map over the modeled names to
  // fractional weights that sum to 1. Non-positive / non-finite entries fall back
  // to equal weight (mirrors factor_exposure.js). Returns { W, isCustom }.
  function normalizeWeights(held, wmap) {
    wmap = wmap || {};
    var n = held.length, eq = n ? 1 / n : 0;
    var raw = held.map(function (t) {
      var v = wmap[t];
      return (isNum(v) && v >= 0) ? v : eq;
    });
    var tot = raw.reduce(function (a, b) { return a + b; }, 0) || 1;
    var W = {};
    held.forEach(function (t, i) { W[t] = raw[i] / tot; });
    var isCustom = held.some(function (t) { return wmap[t] != null; });
    return { W: W, isCustom: isCustom };
  }

  // F·v for the (near-diagonal) factor covariance, F stored as {k -> {j -> cov}}.
  function covApply(keys, cov, vec) {
    var out = {};
    keys.forEach(function (k) {
      var row = cov[k] || {}, s = 0;
      keys.forEach(function (j) { s += (row[j] || 0) * (vec[j] || 0); });
      out[k] = s;
    });
    return out;
  }

  // quadratic form a'F b  (a, b keyed by factor)
  function covQuad(keys, cov, a, b) {
    var Fb = covApply(keys, cov, b), s = 0;
    keys.forEach(function (k) { s += (a[k] || 0) * Fb[k]; });
    return s;
  }

  // ---- coverage split -----------------------------------------------------
  // Split a weights map into modeled (present in betas) vs unmodeled names, and
  // report the unmodeled DOLLAR fraction (over the raw values, before renorm:
  // an unmodeled name can't get a beta but its dollars still count as "book I
  // can't read"). Names with non-positive/absent value contribute 0 dollars.
  function coverage(data, wmap) {
    var betas = data.betas || {};
    wmap = wmap || {};
    var modeled = [], unmodeled = [], modeledDollars = 0, unmodeledDollars = 0;
    Object.keys(wmap).forEach(function (t) {
      var v = wmap[t]; var d = (isNum(v) && v > 0) ? v : 0;
      if (betas[t]) { modeled.push(t); modeledDollars += d; }
      else { unmodeled.push(t); unmodeledDollars += d; }
    });
    var totalDollars = modeledDollars + unmodeledDollars;
    var unmodeledFrac = totalDollars > 0 ? unmodeledDollars / totalDollars
      : (unmodeled.length / (unmodeled.length + modeled.length || 1));
    return {
      modeled: modeled, unmodeled: unmodeled,
      modeledDollars: modeledDollars, unmodeledDollars: unmodeledDollars,
      unmodeledFrac: unmodeledFrac,
      abstain: unmodeledFrac > ABSTAIN_UNMODELED
    };
  }

  // ---- stress-lens availability ------------------------------------------
  // The stress cov ships only after the W1 nightly emit; a null (or an explicit
  // stress_meta.available === false) means calm lens only and the UI hides the toggle.
  function stressAvailable(data) {
    if (!data) return false;
    var meta = data.stress_meta;
    if (meta && meta.available === false) return false;
    var sc = data.factor_cov_stress;
    return !!(sc && typeof sc === 'object');
  }
  // pick the factor covariance for a lens ('calm' | 'stress'); falls back to calm
  // when stress is unavailable so callers never crash on a missing emit.
  function covFor(data, lens) {
    if (lens === 'stress' && stressAvailable(data)) return data.factor_cov_stress;
    return data.factor_cov;
  }

  // =========================================================================
  //  book(): the full book-structure read under ONE lens.
  //  inputs: data (factor_betas.json), wmap {ticker->dollarValue}, lens.
  //  returns { ok, ...reads } or { ok:false, reason, coverage }.
  // =========================================================================
  function book(data, wmap, lens) {
    lens = lens === 'stress' ? 'stress' : 'calm';
    if (!data || !data.factors || !data.betas || !data.factor_cov) {
      return { ok: false, reason: 'no-model' };
    }
    var keys = factorKeys(data);
    var betas = data.betas;
    var cov = covFor(data, lens);
    var cvg = coverage(data, wmap);
    var held = cvg.modeled;
    if (held.length < 2) {
      return { ok: false, reason: 'thin', coverage: cvg, held: held };
    }

    var nw = normalizeWeights(held, wmap);
    var W = nw.W;

    // book factor beta β_book = Σ w_i b_i
    var bp = {};
    keys.forEach(function (k) {
      var s = 0; held.forEach(function (t) { s += W[t] * ((betas[t][k]) || 0); });
      bp[k] = s;
    });
    // Fβ and the factor / idio variance decomposition
    var Fbp = covApply(keys, cov, bp);
    var factorVar = 0; keys.forEach(function (k) { factorVar += bp[k] * Fbp[k]; });
    var idioVar = 0, idioByName = {};
    held.forEach(function (t) {
      var iv = betas[t].idio_vol || 0;
      var c = W[t] * W[t] * iv * iv;
      idioByName[t] = c; idioVar += c;
    });
    var V = factorVar + idioVar;
    var sigmaBook = Math.sqrt(Math.max(V, 0));

    // ---- factor variance shares (Euler): s_k = β_k (Fβ)_k / V ------------
    // Clamp tiny negatives to 0 (near-diagonal F can produce a small negative on
    // a factor the book is net-flat on); disclose if the clamped magnitude is
    // material (> 2% of total). Idio shares are per-name and always ≥ 0.
    var factorShareRaw = {}, clampedMass = 0, sharesDenomRaw = 0;
    keys.forEach(function (k) {
      var contrib = bp[k] * Fbp[k];
      factorShareRaw[k] = contrib;
      if (contrib < 0) clampedMass += -contrib;
      sharesDenomRaw += Math.abs(contrib);
    });
    var factorShare = {};
    keys.forEach(function (k) {
      factorShare[k] = V > 0 ? Math.max(0, factorShareRaw[k]) / V : 0;
    });
    var idioShareTotal = V > 0 ? idioVar / V : 0;
    var idioShare = {};
    held.forEach(function (t) { idioShare[t] = V > 0 ? idioByName[t] / V : 0; });
    var clampDisclose = (sharesDenomRaw > 0)
      && (clampedMass / sharesDenomRaw > CLAMP_DISCLOSE);

    // ranked factors by share (for the "what drives your swings" panel)
    var rankedFactors = keys.slice().sort(function (a, b) {
      return factorShare[b] - factorShare[a];
    });
    var topFactor = rankedFactors[0];
    var topFactorShare = factorShare[topFactor] || 0;

    // ---- ENB = 1 / Σ s_j²  over {factor buckets + PER-NAME idio buckets} --
    // Renormalize the non-negative shares to sum to 1 before inverse-Simpson so
    // a clamped/rounding gap can't inflate or deflate the count.
    var buckets = [];
    keys.forEach(function (k) { buckets.push(factorShare[k]); });
    held.forEach(function (t) { buckets.push(idioShare[t]); });
    var bsum = buckets.reduce(function (a, b) { return a + b; }, 0) || 1;
    var hhi = 0;
    buckets.forEach(function (s) { var p = s / bsum; hhi += p * p; });
    var enb = hhi > 0 ? 1 / hhi : 0;

    // ---- pairwise implied correlation + twin clusters --------------------
    // σ_i² = b_i'F b_i + σ²_ε,i (single-name total vol under this lens); ρ_ij =
    // b_i'F b_j / (σ_i σ_j). Twins = connected components of the ρ ≥ 0.70 graph.
    var sigma = {};
    held.forEach(function (t) {
      var b = betas[t];
      var fv = covQuad(keys, cov, b, b);
      var iv = b.idio_vol || 0;
      sigma[t] = Math.sqrt(Math.max(fv + iv * iv, 0));
    });
    function rho(a, c) {
      var sa = sigma[a], sc = sigma[c];
      if (!(sa > 0) || !(sc > 0)) return 0;
      return covQuad(keys, cov, betas[a], betas[c]) / (sa * sc);
    }
    // adjacency at threshold, then union-find connected components
    var parent = {}; held.forEach(function (t) { parent[t] = t; });
    function find(x) { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; }
    function union(a, c) { var ra = find(a), rc = find(c); if (ra !== rc) parent[ra] = rc; }
    var pairs = [];
    for (var i = 0; i < held.length; i++) {
      for (var j = i + 1; j < held.length; j++) {
        var r = rho(held[i], held[j]);
        if (r >= TWIN_RHO) { union(held[i], held[j]); pairs.push({ a: held[i], b: held[j], rho: r }); }
      }
    }
    var compMap = {};
    held.forEach(function (t) {
      var rootT = find(t);
      (compMap[rootT] = compMap[rootT] || []).push(t);
    });
    // clusters of size ≥ 2 (a real twin group); carry the members' summed |MCTR|
    // later so the caller can size the bus segments. Singletons are their own bet.
    var clusters = Object.keys(compMap).map(function (rootT) {
      return { members: compMap[rootT] };
    });

    // ---- per-position risk contribution (MCTR share) ---------------------
    // (Σ w)_i = Σ_j w_j Cov(i,j), Cov = B F B' + D restricted to the book;
    // MCTR_i = w_i (Σ w)_i, share_i = MCTR_i / V (Σ_i share_i = 1). Negative =
    // the position moves against the book (a hedge).
    var Fbeta = covApply(keys, cov, bp);   // = F·β_book (reused for the cross term)
    var mctr = {}, mctrShare = {};
    held.forEach(function (t) {
      var b = betas[t];
      // Cov(i, book) = b_i'·(F·β_book) + w_i·σ²_ε,i   (idio only self-couples)
      var factorCross = 0;
      keys.forEach(function (k) { factorCross += (b[k] || 0) * Fbeta[k]; });
      var iv = b.idio_vol || 0;
      var covIBook = factorCross + W[t] * iv * iv;
      var contrib = W[t] * covIBook;                 // MCTR_i (variance units)
      mctr[t] = contrib;
      mctrShare[t] = V > 0 ? contrib / V : 0;
    });
    // sanity: Σ MCTR ≈ V (variance additivity of the Euler decomposition)
    var mctrSum = 0; held.forEach(function (t) { mctrSum += mctr[t]; });

    var rankedPositions = held.slice().sort(function (a, b) {
      return Math.abs(mctrShare[b]) - Math.abs(mctrShare[a]);
    });

    return {
      ok: true, lens: lens, held: held, W: W, isCustom: nw.isCustom,
      keys: keys, coverage: cvg,
      __meta: { betas: betas, cov: cov },   // raw refs for factorBets() (per-name split)
      bookBeta: bp, factorVar: factorVar, idioVar: idioVar,
      variance: V, sigma: sigmaBook,
      factorShare: factorShare, idioShare: idioShare, idioShareTotal: idioShareTotal,
      clampedShareMass: sharesDenomRaw > 0 ? clampedMass / sharesDenomRaw : 0,
      clampDisclose: clampDisclose,
      rankedFactors: rankedFactors, topFactor: topFactor, topFactorShare: topFactorShare,
      enb: enb,
      sigmaByName: sigma, rho: rho, twinPairs: pairs, clusters: clusters,
      mctr: mctr, mctrShare: mctrShare, mctrSum: mctrSum,
      rankedPositions: rankedPositions
    };
  }

  // =========================================================================
  //  read(): both lenses + the calm↔stress divergence flag, in one call.
  //  The surface's default read is the stress lens when it's available (WRI-R7).
  // =========================================================================
  function read(data, wmap) {
    var hasStress = stressAvailable(data);
    var calm = book(data, wmap, 'calm');
    var stress = hasStress ? book(data, wmap, 'stress') : null;

    // divergence: stress ENB materially below calm ENB, or a twin pair that only
    // appears under stress (a name that decouples on calm days but joins in selloffs).
    var diverges = false, stressOnlyPairs = [];
    if (calm.ok && stress && stress.ok) {
      if (stress.enb < 0.7 * calm.enb) diverges = true;
      var calmSet = {};
      calm.twinPairs.forEach(function (p) { calmSet[p.a + '|' + p.b] = 1; calmSet[p.b + '|' + p.a] = 1; });
      stress.twinPairs.forEach(function (p) {
        if (!calmSet[p.a + '|' + p.b]) { stressOnlyPairs.push(p); diverges = true; }
      });
    }
    return {
      hasStress: hasStress, calm: calm, stress: stress,
      diverges: diverges, stressOnlyPairs: stressOnlyPairs,
      // the default lens the surface leads with
      defaultLens: hasStress ? 'stress' : 'calm'
    };
  }

  // =========================================================================
  //  factorBets(): group the book's names into "bets" for the patch-bay PICTURE.
  //  A name joins its single dominant factor's bet when that factor is at least
  //  `floor` of the name's own variance; otherwise the name is its own
  //  (idiosyncratic) bet. This is the visual composition of the book — WHERE the
  //  risk sits — distinct from ENB (how many EFFECTIVELY-independent bets, which
  //  weights by variance) and from ρ≥0.70 twins (names that literally track each
  //  other). Returns [{ key, factor|null, members[], share (|MCTR| summed) }],
  //  sorted by share desc (dominant bet first). Pure — takes a book() result.
  // =========================================================================
  function factorBets(b, floor) {
    if (!b || !b.ok) return [];
    floor = (typeof floor === 'number') ? floor : 0.25;
    var keys = b.keys, cov = null;   // per-name variance from the book's sigmaByName
    var groups = {}, order = [];
    b.held.forEach(function (t) {
      // dominant factor of THIS name = argmax of its factor variance contribution;
      // reuse sigmaByName (total) and recompute the per-name factor split cheaply.
      var sig = b.sigmaByName[t] || 0;
      var tot = sig * sig || 1;
      // factor variance contributions need the betas + cov; the book already holds
      // rho() which uses them, but we want per-name factor split — approximate via
      // the book's factorShare weighting is wrong per-name, so recompute here using
      // the same near-diagonal structure the caller passed in `bookMeta`.
      var meta = b.__meta;   // { betas, cov, idioByName? }
      var domF = null, domShare = 0;
      if (meta) {
        var betas = meta.betas, F = meta.cov, bt = betas[t] || {};
        keys.forEach(function (k) {
          var v = (bt[k] || 0) * (bt[k] || 0) * ((F[k] && F[k][k]) || 0);
          if (v > domShare) { domShare = v; domF = k; }
        });
        domShare = domShare / tot;
      }
      var key = (domF && domShare >= floor) ? domF : ('idio:' + t);
      if (!groups[key]) { groups[key] = { key: key, factor: (domF && domShare >= floor) ? domF : null, members: [], share: 0 }; order.push(key); }
      groups[key].members.push(t);
      groups[key].share += Math.abs(b.mctrShare[t] || 0);
    });
    var arr = order.map(function (k) { return groups[k]; });
    arr.sort(function (a, c) { return c.share - a.share; });
    return arr;
  }

  // ENB -> named state (stress lens drives the chip; thresholds are heuristic v0,
  // printed in the ? receipt). Kept here so the render layer and tests agree.
  //   ≥ 4 spread / 2.5–4 leaning / 1.5–2.5 mostly-one / < 1.5 one-bet
  function enbState(enb) {
    if (!isNum(enb)) return 'na';
    if (enb >= 4) return 'ok';
    if (enb >= 2.5) return 'tilt';
    if (enb >= 1.5) return 'conc';
    return 'one';
  }

  var api = {
    book: book, read: read, factorBets: factorBets,
    coverage: coverage, stressAvailable: stressAvailable, covFor: covFor,
    normalizeWeights: normalizeWeights, enbState: enbState,
    TWIN_RHO: TWIN_RHO, ABSTAIN_UNMODELED: ABSTAIN_UNMODELED
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.RiskCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
