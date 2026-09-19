from decimal import Decimal

import pytest

from app.calculation import (
    CalculationValidationError,
    SteadyInput,
    calculate_steady_state,
)


def base_input(**overrides) -> SteadyInput:
    values = {
        "c0": Decimal("10"),
        "g": Decimal("1.5"),
        "eta_mau": Decimal("0.72"),
        "cov_mau": Decimal("1"),
        "eta_ceil": Decimal("0.55"),
        "cov_ceil": Decimal("0.92"),
        "eta_aru": Decimal("0.35"),
        "cov_aru": Decimal("0.8"),
        "alpha": Decimal("0.3"),
        "beta": Decimal("0.7"),
        "target_value": Decimal("3.2"),
    }
    values.update(overrides)
    return SteadyInput(**values)


def test_converges_to_closed_form_and_passes() -> None:
    data = base_input()
    result = calculate_steady_state(data)
    c1 = data.c0 * (1 - data.eta_mau * data.cov_mau)
    ceiling = 1 - data.eta_ceil * data.cov_ceil
    return_factor = 1 - data.eta_aru * data.cov_aru
    expected = (data.alpha * c1 * ceiling + data.alpha * data.g) / (
        1 - data.beta * return_factor * ceiling
    )

    assert result.converged is True
    assert result.conclusion == "pass"
    assert abs(result.nodes_internal["cr"] - expected) <= data.epsilon
    assert result.iter_count <= 200


def test_ppb_conversion_preserves_internal_result() -> None:
    internal = calculate_steady_state(base_input())
    factor = Decimal("24.04") / Decimal("30.03")
    ppb = calculate_steady_state(base_input(
        c0=Decimal("10") * factor,
        g=Decimal("1.5") * factor,
        target_value=Decimal("3.2") * factor,
        conc_unit="ppb",
        molar_mass_m=Decimal("30.03"),
    ))
    assert abs(ppb.nodes_internal["cr"] - internal.nodes_internal["cr"]) <= Decimal("1e-27")


def test_degenerate_mapping_is_not_false_convergence() -> None:
    result = calculate_steady_state(base_input(
        alpha=Decimal("0"), beta=Decimal("1"),
        eta_ceil=Decimal("0"), cov_ceil=Decimal("0"),
        eta_aru=Decimal("0"), cov_aru=Decimal("0"),
    ))
    assert result.converged is False
    assert result.conclusion == "error"
    assert result.error_code == "DEGENERATE_NO_UNIQUE_STEADY_STATE"


def test_max_iteration_failure_has_no_pass_fail_conclusion() -> None:
    result = calculate_steady_state(base_input(max_iterations=1, epsilon=Decimal("1e-30")))
    assert result.converged is False
    assert result.conclusion == "not_converged"
    assert result.error_code == "MAX_ITERATIONS_EXCEEDED"


def test_rejects_invalid_air_ratio() -> None:
    with pytest.raises(CalculationValidationError):
        calculate_steady_state(base_input(alpha=Decimal("0.4"), beta=Decimal("0.7")))


@pytest.mark.parametrize(
    ("data", "excel_cr"),
    [
        (
            base_input(
                c0=Decimal("5"), g=Decimal("9"), eta_mau=Decimal("0"), cov_mau=Decimal("0"),
                eta_ceil=Decimal("0.9"), cov_ceil=Decimal("1"), eta_aru=Decimal("0"),
                cov_aru=Decimal("0"), alpha=Decimal("0.2"), beta=Decimal("0.8"),
                target_value=None,
            ),
            Decimal("2.0652173913043477"),
        ),
        (
            base_input(
                c0=Decimal("6"), g=Decimal("2"), eta_mau=Decimal("0.5"), cov_mau=Decimal("1"),
                eta_ceil=Decimal("0.7"), cov_ceil=Decimal("0.5"), eta_aru=Decimal("0"),
                cov_aru=Decimal("0"), alpha=Decimal("0.2"), beta=Decimal("0.8"),
                target_value=None,
            ),
            Decimal("1.645833340172587"),
        ),
    ],
)
def test_customer_excel_baselines(data: SteadyInput, excel_cr: Decimal) -> None:
    result = calculate_steady_state(data)
    relative_error = abs(result.nodes_internal["cr"] - excel_cr) / abs(excel_cr)
    assert result.converged is True
    assert relative_error <= Decimal("1e-6")
