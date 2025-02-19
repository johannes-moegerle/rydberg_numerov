from typing import Literal, Union

import numpy as np

from numerov.angular.utils import calc_wigner_3j, calc_wigner_6j, check_triangular, minus_one_pow

OperatorType = Literal["L", "S", "Y", "p", "mu"]


def calc_angular_matrix_element(
    s1: float,
    l1: int,
    j1: float,
    m1: float,
    s2: float,
    l2: int,
    j2: float,
    m2: float,
    operator: OperatorType,
    kappa: int,
    q: int,
) -> float:
    r"""Calculate the angular matrix element $\bra{state_2} \hat{O}_{kq} \ket{state_1}$.

    For the states $\bra{state_2} = \bra{s2,l2,j2,m2}$ and $\ket{state_1} = \ket{s1,l1,j1,m1}$,
    the angular matrix elements of the angular momentum operators $\hat{O}_{kq}$ are given by

    .. math::
        \bra{state_2} \hat{O}_{kq} \ket{state_1}
        = \bra{s2,l2,j2,m2} \hat{O}_{kq} \ket{s1,l1,j1,m1}
        = \langle j1, m1, k, q | j2, m2 \rangle \langle j2 || \hat{O}_{k0} || j1 \rangle / \sqrt{2 * j2 + 1}
        = (-1)^{j1 - \kappa + m2} wigner_3j(j1, kappa, j2, m1, q, -m2)
        \langle j2 || \hat{O}_{k0} || j1 \rangle

    where we first used the Wigner-Eckhart theorem
    and then the Wigner 3-j symbol to express the Clebsch-Gordan coefficient.

    Note we changed the formulas to match the pairinteraction paper convention:
    https://doi.org/10.1088/1361-6455/aa743a

    Args:
        s1: The spin quantum number of the initial state.
        l1: The orbital quantum number of the initial state.
        j1: The total angular momentum quantum number of the initial state.
        m1: The magnetic quantum number of the initial state.
        s2: The spin quantum number of the final state.
        l2: The orbital quantum number of the final state.
        j2: The total angular momentum quantum number of the final state.
        m2: The magnetic quantum number of the final state.
        operator: The angular momentum operator type $\hat{O}_{kq}$.
            Can be one of the following:
                - "L" for the orbital angular momentum operator,
                - "S" for the spin angular momentum operator,
                - "Y" for the spherical harmonics operator,
                - "p" for the spherical multipole operator.
                - "mu" for the magnetic moment operator.
        kappa: The quantum number $\kappa$ of the angular momentum operator.
        q: The quantum number $q$ of the angular momentum operator.

    Returns:
        The angular matrix element $\bra{state_2} \hat{O}_{kq} \ket{state_1}$.

    """
    prefactor = minus_one_pow(j2 - m2)
    reduced_matrix_element = calc_reduced_angular_matrix_element(s1, l1, j1, s2, l2, j2, operator, kappa)
    wigner_3j = calc_wigner_3j(j2, kappa, j1, -m2, q, m1)
    return prefactor * reduced_matrix_element * wigner_3j


def calc_reduced_angular_matrix_element(
    s1: float,
    l1: int,
    j1: float,
    s2: float,
    l2: int,
    j2: float,
    operator: OperatorType,
    kappa: int,
    _lazy_evaluation: bool = True,
) -> float:
    r"""Calculate the reduced matrix element $\langle j2 || \hat{O}_{k0} || j1 \rangle$.

    The reduced matrix elements $\langle j2 || \hat{O}_{k0} || j1 \rangle$ for
    $\bra{j2} = \bra{\gamma_2, s2, l2, j2}$ and $\ket{j1} = \ket{\gamma_1, s1, l1, j1}$
    simplify for the special cases $s2 = s1$ or $l2 = l1$ to the following expressions:
    (see https://www.phys.ksu.edu/reu2015/danielkeylon/Wigner.pdf, and Edmonds: "Angular Momentum in Quantum Mechanics")

    For $s2 = s1$ (i.e. when \hat{O}_{k0} only acts on l), the reduced matrix element is given by
    .. math::
        \langle \gamma_2, s2, l2, j2 || \hat{O}_{k0} || \gamma_1, s2, l1, j1 \rangle
        = (-1)**(s2 + l2 + j1 + kappa) sqrt{2j + 1} sqrt{2j1 + 1} wigner_6j(l2, j2, s2, j1, l1, kappa)
        \langle \gamma_2, l2 || \hat{O}_{k0} || \gamma_1, l1 \rangle

    And for $l2 = l1$ (i.e. when \hat{O}_{k0} only acts on s), the reduced matrix element is given by
    .. math::
        \langle \gamma_2, s2, l2, j2 || \hat{O}_{k0} || \gamma_1, s1, l2, j1 \rangle
        = (-1)**(s2 + l2 + j1 + kappa) sqrt{2j + 1} sqrt{2 * j1 + 1} wigner_6j(s2, j2, l2, j1, s1, kappa)
        \langle \gamma_2, s2 || \hat{O}_{k0} || \gamma_1, s1 \rangle

    Note we changed the formulas to match the pairinteraction paper convention:
    https://doi.org/10.1088/1361-6455/aa743a

    Args:
        s1: The spin quantum number of the initial state.
        l1: The orbital quantum number of the initial state.
        j1: The total angular momentum quantum number of the initial state.
        s2: The spin quantum number of the final state.
        l2: The orbital quantum number of the final state.
        j2: The total angular momentum quantum number of the final state.
        operator: The angular momentum operator $\hat{O}_{kq}$.
        kappa: The quantum number $\kappa$ of the angular momentum operator.

    Returns:
        The reduced matrix element $\langle j2 || \hat{O}_{k0} || j1 \rangle$.

    """
    assert operator in ["L", "S", "Y", "p", "mu"]

    should_be_zero = False
    if not check_triangular(j2, j1, kappa):
        should_be_zero = True
    elif operator in ["Y", "p", "L"] and not check_triangular(l2, l1, kappa):
        should_be_zero = True
    elif operator in ["S"] and not check_triangular(s2, s1, kappa):
        should_be_zero = True
    elif operator in ["p", "Y"] and (l2 + l1 + kappa) % 2 != 0:
        should_be_zero = True
    elif operator in ["L", "S", "mu"] and (l2 != l1 or s2 != s1):
        should_be_zero = True
    elif (operator == "S" and s2 == 0) or (operator == "L" and l2 == 0):
        should_be_zero = True

    if should_be_zero and _lazy_evaluation:
        return 0

    if operator == "mu":
        mu_B = 0.5  # Bohr magneton in atomic units
        g_s = 2.0023192
        value_s = calc_reduced_angular_matrix_element(s1, l1, j1, s2, l2, j2, "S", kappa)
        g_l = 1
        value_l = calc_reduced_angular_matrix_element(s1, l1, j1, s2, l2, j2, "L", kappa)
        mu = mu_B * (
            g_s * value_s + g_l * value_l
        )  # TODO note the missing minus is convention how we use it in pairinteraction ...
        return mu

    prefactor = np.sqrt(2 * j1 + 1) * np.sqrt(2 * j2 + 1)

    reduced_matrix_element: float
    if operator == "S":
        prefactor *= minus_one_pow(l2 + s1 + j2 + kappa)
        if l1 != l2:
            reduced_matrix_element = 0
        else:
            reduced_matrix_element = momentum_matrix_element(s1, s2, kappa)
        wigner_6j = calc_wigner_6j(s2, j2, l2, j1, s1, kappa)
    else:
        prefactor *= minus_one_pow(l2 + s2 + j1 + kappa)
        if operator == "L":
            if s1 != s2:
                reduced_matrix_element = 0
            else:
                reduced_matrix_element = momentum_matrix_element(l1, l2, kappa)
        else:
            reduced_matrix_element = multipole_matrix_element(l1, l2, operator, kappa)
        wigner_6j = calc_wigner_6j(l2, j2, s2, j1, l1, kappa)

    value = prefactor * reduced_matrix_element * wigner_6j

    # Check that we catched all cases where the reduced matrix element is zero before
    if should_be_zero and value != 0:
        raise ValueError(
            f"The reduced angular matrix element for {(s1, l1, j1)}, {(s2, l2, j2)}, {operator}, {kappa} "
            "is not zero (but should be zero)."
        )
    if value == 0 and not should_be_zero:
        raise ValueError(
            f"The reduced angular matrix element for {(s1, l1, j1)}, {(s2, l2, j2)}, {operator}, {kappa}"
            "is zero (but should not be zero)."
        )

    return value


def momentum_matrix_element(x1: Union[int, float], x2: Union[int, float], kappa: int) -> float:
    r"""Calculate the reduced matrix element $(x2||\hat{x}_{10}||x1)$ for a momentum operator.

    The matrix elements of the momentum operators $x \in \{l, s\}$ are given by

    .. math::
        (x2||\hat{x}_{10}||x1) = \delta_{x2, x1} \sqrt{x1 (x1 + 1) (2 * x1 + 1)}

    Args:
        x1: The angular momentum quantum number of the initial state.
        x2: The angular momentum quantum number of the final state.
        kappa: The quantum number $\kappa$ of the angular momentum operator.

    Returns:
        The reduced matrix element $(x2||\hat{x}_{10}||x1)$.

    """
    if x1 != x2 or x1 == 0:
        return 0
    if kappa == 1:
        return np.sqrt(x1 * (x1 + 1) * (2 * x1 + 1))
    raise NotImplementedError("Currently only kappa=1 is supported.")


def multipole_matrix_element(l1: int, l2: int, operator: OperatorType, kappa: int) -> float:
    r"""Calculate the reduced matrix element $(l2||\hat{p}_{k0}||l1)$ for the multipole operator.

    The matrix elements of the multipole operators are given by (see also: Gaunt coefficient)

    .. math::
        (l2||\hat{p}_{k0}||l1) = (-1)^l2 \sqrt{(2 * l2 + 1)(2 * l1 + 1)}
                                    \begin{pmatrix} l2 & k & l1 \\ 0 & 0 & 0 \end{pmatrix}

    Args:
        l1: The oribtal momentum quantum number of the initial state.
        l2: The oribtal momentum quantum number of the final state.
        operator: The multipole operator, either "Y" or "p".
        kappa: The quantum number $\kappa$ of the angular momentum operator.

    Returns:
        The reduced matrix element $(l2||\hat{p}_{k0}||l1)$.

    """
    assert operator in ["Y", "p"]

    prefactor = minus_one_pow(l2)
    prefactor *= np.sqrt((2 * l1 + 1) * (2 * l2 + 1))
    if operator == "Y":
        prefactor *= np.sqrt((2 * kappa + 1) / (4 * np.pi))

    wigner_3j = calc_wigner_3j(l2, kappa, l1, 0, 0, 0)
    return prefactor * wigner_3j
