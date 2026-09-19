from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any


ZERO = Decimal("0")
ONE = Decimal("1")
DEFAULT_EPSILON = Decimal("0.000001")
DEFAULT_MAX_ITERATIONS = 200
DEFAULT_MOLAR_VOLUME = Decimal("24.04")
ALGO_VERSION = "steady-v1.0"


class CalculationValidationError(ValueError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class SteadyInput:
    c0: Decimal
    g: Decimal
    eta_mau: Decimal
    cov_mau: Decimal
    eta_ceil: Decimal
    cov_ceil: Decimal
    eta_aru: Decimal
    cov_aru: Decimal
    alpha: Decimal
    beta: Decimal
    conc_unit: str = "ugm3"
    molar_mass_m: Decimal | None = None
    molar_volume_vm: Decimal = DEFAULT_MOLAR_VOLUME
    target_value: Decimal | None = None
    epsilon: Decimal = DEFAULT_EPSILON
    max_iterations: int = DEFAULT_MAX_ITERATIONS


@dataclass(frozen=True)
class Iteration:
    iter_no: int
    cr_old: Decimal
    c1: Decimal
    c_return: Decimal
    cmix: Decimal
    cout2: Decimal
    cr_new: Decimal
    delta: Decimal


@dataclass(frozen=True)
class CalculationResult:
    converged: bool
    iter_count: int
    algo_version: str
    unit: str
    nodes_internal: dict[str, Decimal]
    nodes: dict[str, Decimal]
    iterations_internal: list[Iteration]
    iterations: list[Iteration]
    conclusion: str
    target_value: Decimal | None
    target_internal: Decimal | None
    epsilon: Decimal
    error_code: str | None = None
    error_message: str | None = None


def decimal_value(value: Any, field: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CalculationValidationError(f"{field} 必须是有效数字", field=field) from exc
    if not number.is_finite():
        raise CalculationValidationError(f"{field} 必须是有限数字", field=field)
    return number


def normalize_unit(unit: str) -> str:
    normalized = {"ug": "ugm3", "μg/m³": "ugm3", "ug/m3": "ugm3"}.get(unit, unit)
    if normalized not in {"ppb", "ugm3"}:
        raise CalculationValidationError("concUnit 仅支持 ppb 或 ug", field="concUnit")
    return normalized


def validate_input(data: SteadyInput) -> None:
    for field in ("c0", "g"):
        if getattr(data, field) < ZERO:
            raise CalculationValidationError(f"{field} 不能小于 0", field=field)
    for field in (
        "eta_mau", "cov_mau", "eta_ceil", "cov_ceil",
        "eta_aru", "cov_aru", "alpha", "beta",
    ):
        value = getattr(data, field)
        if value < ZERO or value > ONE:
            raise CalculationValidationError(f"{field} 必须在 0 到 1 之间", field=field)
    if abs(data.alpha + data.beta - ONE) > Decimal("1e-10"):
        raise CalculationValidationError("新风比例 alpha 与回风比例 beta 之和必须为 1", field="alpha")
    if data.conc_unit == "ppb" and (data.molar_mass_m is None or data.molar_mass_m <= ZERO):
        raise CalculationValidationError("使用 ppb 时 molarMassM 必须大于 0", field="molarMassM")
    if data.molar_volume_vm <= ZERO:
        raise CalculationValidationError("molarVolumeVm 必须大于 0", field="molarVolumeVm")
    if data.target_value is not None and data.target_value < ZERO:
        raise CalculationValidationError("targetValue 不能小于 0", field="targetValue")
    if data.epsilon <= ZERO:
        raise CalculationValidationError("epsilon 必须大于 0", field="epsilon")
    if data.max_iterations < 1 or data.max_iterations > 10000:
        raise CalculationValidationError("maxIterations 必须在 1 到 10000 之间", field="maxIterations")


def to_internal(value: Decimal, data: SteadyInput) -> Decimal:
    if data.conc_unit == "ppb":
        assert data.molar_mass_m is not None
        return value * data.molar_mass_m / data.molar_volume_vm
    return value


def from_internal(value: Decimal, data: SteadyInput) -> Decimal:
    if data.conc_unit == "ppb":
        assert data.molar_mass_m is not None
        return value * data.molar_volume_vm / data.molar_mass_m
    return value


def _convert_iteration(row: Iteration, data: SteadyInput) -> Iteration:
    return Iteration(
        iter_no=row.iter_no,
        cr_old=from_internal(row.cr_old, data),
        c1=from_internal(row.c1, data),
        c_return=from_internal(row.c_return, data),
        cmix=from_internal(row.cmix, data),
        cout2=from_internal(row.cout2, data),
        cr_new=from_internal(row.cr_new, data),
        delta=from_internal(row.delta, data),
    )


def calculate_steady_state(data: SteadyInput) -> CalculationResult:
    data = SteadyInput(**{**asdict(data), "conc_unit": normalize_unit(data.conc_unit)})
    validate_input(data)

    with localcontext() as context:
        context.prec = 40
        c0 = to_internal(data.c0, data)
        g = to_internal(data.g, data)
        target_internal = None if data.target_value is None else to_internal(data.target_value, data)
        c1 = c0 * (ONE - data.eta_mau * data.cov_mau)
        ceiling_factor = ONE - data.eta_ceil * data.cov_ceil
        return_factor = ONE - data.eta_aru * data.cov_aru
        mapping_slope = data.beta * return_factor * ceiling_factor

        cr_old = c0
        iterations: list[Iteration] = []
        converged = False
        error_code = None
        error_message = None

        for index in range(1, data.max_iterations + 1):
            c_return = cr_old * return_factor
            cmix = data.alpha * c1 + data.beta * c_return
            cout2 = cmix * (ONE - data.eta_ceil)
            cr_new = cmix * ceiling_factor + data.alpha * g
            delta = abs(cr_new - cr_old)
            iterations.append(Iteration(index, cr_old, c1, c_return, cmix, cout2, cr_new, delta))

            # slope=1 时即使首轮数值不变也可能有无穷多个解，不能误判为收敛。
            if mapping_slope >= ONE:
                error_code = "DEGENERATE_NO_UNIQUE_STEADY_STATE"
                error_message = "迭代映射不具收缩性，无法确定唯一稳态解"
                break
            if delta <= data.epsilon:
                converged = True
                break
            cr_old = cr_new

        if not converged and error_code is None:
            error_code = "MAX_ITERATIONS_EXCEEDED"
            error_message = f"在 {data.max_iterations} 次迭代内未达到收敛阈值"

        final = iterations[-1]
        nodes_internal = {
            "c0": c0, "c1": final.c1, "cReturn": final.c_return,
            "cmix": final.cmix, "cout2": final.cout2, "cr": final.cr_new,
        }
        nodes = {key: from_internal(value, data) for key, value in nodes_internal.items()}
        display_iterations = [_convert_iteration(row, data) for row in iterations]
        if not converged:
            conclusion = "error" if error_code == "DEGENERATE_NO_UNIQUE_STEADY_STATE" else "not_converged"
        elif target_internal is None:
            conclusion = "no_standard"
        else:
            conclusion = "pass" if final.cr_new <= target_internal else "fail"

        return CalculationResult(
            converged=converged,
            iter_count=len(iterations),
            algo_version=ALGO_VERSION,
            unit="ug" if data.conc_unit == "ugm3" else data.conc_unit,
            nodes_internal=nodes_internal,
            nodes=nodes,
            iterations_internal=iterations,
            iterations=display_iterations,
            conclusion=conclusion,
            target_value=data.target_value,
            target_internal=target_internal,
            epsilon=data.epsilon,
            error_code=error_code,
            error_message=error_message,
        )


def decimal_strings(values: dict[str, Decimal]) -> dict[str, str]:
    return {key: format(value, "f") for key, value in values.items()}
