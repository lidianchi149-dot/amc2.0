(function (global) {
  'use strict';

  const EPSILON = 1e-6;
  const MAX_ITER = 200;
  const ALGO_VERSION = 'steady-v1.0';

  function finite(value, field) {
    const number = Number(value);
    if (!Number.isFinite(number)) throw new Error(`${field} 必须是有效数字`);
    return number;
  }

  function validate(input) {
    ['etaMau', 'covMau', 'etaCeil', 'covCeil', 'etaAru', 'covAru', 'alpha', 'beta'].forEach((key) => {
      const value = finite(input[key], key);
      if (value < 0 || value > 1) throw new Error(`${key} 必须在 0–1 范围内`);
    });
    ['c0', 'g'].forEach((key) => {
      if (finite(input[key], key) < 0) throw new Error(`${key} 不能小于 0`);
    });
    if (Math.abs(Number(input.alpha) + Number(input.beta) - 1) > 1e-10) {
      const error = new Error('新风比例 α 与回风比例 β 之和必须为 1');
      error.code = 1001;
      throw error;
    }
  }

  function toInternal(value, unit, molarMass, molarVolume) {
    return unit === 'ppb' ? Number(value) * Number(molarMass) / Number(molarVolume) : Number(value);
  }

  function fromInternal(value, unit, molarMass, molarVolume) {
    return unit === 'ppb' ? Number(value) * Number(molarVolume) / Number(molarMass) : Number(value);
  }

  function calculate(payload) {
    const raw = payload.input;
    validate(raw);
    const unit = payload.concUnit || 'ug';
    const molarMass = finite(payload.molarMassM || 1, 'molarMassM');
    const molarVolume = finite(payload.molarVolumeVm || 24.04, 'molarVolumeVm');
    const input = { ...raw, c0: toInternal(raw.c0, unit, molarMass, molarVolume), g: toInternal(raw.g, unit, molarMass, molarVolume) };
    const targetInternal = payload.targetValue === null || payload.targetValue === '' || payload.targetValue === undefined
      ? null : toInternal(payload.targetValue, unit, molarMass, molarVolume);
    const c1 = input.c0 * (1 - input.etaMau * input.covMau);
    let crOld = input.c0;
    let nodes = null;
    const iterations = [];
    let converged = false;

    for (let index = 1; index <= (payload.maxIter || MAX_ITER); index += 1) {
      const cReturn = crOld * (1 - input.etaAru * input.covAru);
      const cmix = input.alpha * c1 + input.beta * cReturn;
      const cout2 = cmix * (1 - input.etaCeil);
      const crNew = cmix * (1 - input.etaCeil * input.covCeil) + input.alpha * input.g;
      nodes = { c0: input.c0, c1, cReturn, cmix, cout2, cr: crNew };
      iterations.push({ iterNo: index, crOld, c1, cReturn, cmix, cout2, crNew });
      if (Math.abs(crNew - crOld) <= (payload.epsilon || EPSILON)) { converged = true; break; }
      crOld = crNew;
    }

    const displayNodes = Object.fromEntries(Object.entries(nodes).map(([key, value]) => [key, fromInternal(value, unit, molarMass, molarVolume)]));
    const displayIterations = iterations.map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, key === 'iterNo' ? value : fromInternal(value, unit, molarMass, molarVolume)])));
    const conclusion = targetInternal === null ? 'no_standard' : (nodes.cr <= targetInternal ? 'pass' : 'fail');
    return {
      converged,
      iterCount: iterations.length,
      algoVersion: ALGO_VERSION,
      nodes: displayNodes,
      nodesInternal: nodes,
      unit,
      conclusion,
      targetValue: payload.targetValue === '' ? null : payload.targetValue,
      iterations: displayIterations,
      inputSnapshot: JSON.parse(JSON.stringify(payload)),
      epsilon: payload.epsilon || EPSILON
    };
  }

  global.AMCEngine = { calculate, validate, constants: { EPSILON, MAX_ITER, ALGO_VERSION } };
})(window);
