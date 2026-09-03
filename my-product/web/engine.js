(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.AMCEngine = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  const VERSION = "steady-v1.0";
  const DEFAULT_EPSILON = 1e-6;
  const DEFAULT_MAX_ITERATIONS = 200;

  function assertFinite(name, value) {
    if (!Number.isFinite(value)) throw new Error(`${name} 必须是有效数字`);
  }

  function validate(input) {
    const required = ["c0", "g", "etaMau", "covMau", "etaCeil", "covCeil", "etaAru", "covAru", "alpha", "beta"];
    required.forEach((key) => assertFinite(key, input[key]));
    if (input.c0 < 0 || input.g < 0) throw new Error("C0 与 G 不能小于 0");
    ["etaMau", "covMau", "etaCeil", "covCeil", "etaAru", "covAru", "alpha", "beta"].forEach((key) => {
      if (input[key] < 0 || input[key] > 1) throw new Error(`${key} 必须在 0 到 1 之间`);
    });
    if (Math.abs(input.alpha + input.beta - 1) > 1e-10) throw new Error("新风比 α 与回风比 β 之和必须为 1");
  }

  function calculate(input, options) {
    validate(input);
    const epsilon = options?.epsilon ?? DEFAULT_EPSILON;
    const maxIterations = options?.maxIterations ?? DEFAULT_MAX_ITERATIONS;
    const c1 = input.c0 * (1 - input.etaMau * input.covMau);
    const returnFactor = 1 - input.etaAru * input.covAru;
    const ceilingFactor = 1 - input.etaCeil * input.covCeil;
    const mappingFactor = input.beta * returnFactor * ceilingFactor;
    const sourceTerm = input.alpha * c1 * ceilingFactor + input.alpha * input.g;

    if (Math.abs(1 - mappingFactor) < 1e-12) {
      return {
        status: "degenerate",
        message: Math.abs(sourceTerm) < 1e-12 ? "当前参数存在无唯一稳态解的退化工况" : "当前参数不具备有限稳态解",
        version: VERSION,
        iterations: [], c1, epsilon, maxIterations
      };
    }

    let oldCr = input.c0;
    const iterations = [];
    for (let i = 1; i <= maxIterations; i += 1) {
      const cReturn = oldCr * returnFactor;
      const cMix = input.alpha * c1 + input.beta * cReturn;
      const cOut2 = cMix * (1 - input.etaCeil);
      const newCr = cMix * ceilingFactor + input.alpha * input.g;
      const delta = Math.abs(newCr - oldCr);
      iterations.push({ index: i, oldCr, cReturn, cMix, cOut2, cr: newCr, delta });
      if (![cReturn, cMix, cOut2, newCr, delta].every(Number.isFinite)) {
        return { status: "error", message: "计算出现非有限数值", version: VERSION, iterations, c1, epsilon, maxIterations };
      }
      if (delta <= epsilon) {
        return {
          status: "converged", message: "计算已收敛", version: VERSION,
          iterationCount: i, iterations, c1, cReturn, cMix, cOut2, cr: newCr,
          epsilon, maxIterations, mappingFactor
        };
      }
      oldCr = newCr;
    }
    const last = iterations[iterations.length - 1];
    return {
      status: "not_converged", message: `在 ${maxIterations} 次迭代内未达到收敛阈值`, version: VERSION,
      iterationCount: maxIterations, iterations, c1, cReturn: last.cReturn, cMix: last.cMix,
      cOut2: last.cOut2, cr: last.cr, epsilon, maxIterations, mappingFactor
    };
  }

  function ppbToUg(value, molarMass, molarVolume) {
    [value, molarMass, molarVolume].forEach((item, index) => assertFinite(["浓度", "摩尔质量", "摩尔体积"][index], item));
    if (molarVolume <= 0) throw new Error("摩尔体积必须大于 0");
    return value * molarMass / molarVolume;
  }

  function ugToPpb(value, molarMass, molarVolume) {
    [value, molarMass, molarVolume].forEach((item, index) => assertFinite(["浓度", "摩尔质量", "摩尔体积"][index], item));
    if (molarMass <= 0) throw new Error("摩尔质量必须大于 0");
    return value * molarVolume / molarMass;
  }

  return { VERSION, DEFAULT_EPSILON, DEFAULT_MAX_ITERATIONS, validate, calculate, ppbToUg, ugToPpb };
});
