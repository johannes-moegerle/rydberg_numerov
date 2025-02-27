import logging
from dataclasses import dataclass
from typing import Literal, Optional, Union

import numexpr as ne
import numpy as np

from numerov.model.database import Database
from numerov.units import ureg

logger = logging.getLogger(__name__)


class InvalidStateError(Exception):
    """Exception raised when the specified state does not exist because it is below the ground state."""

    pass


@dataclass
class Model:
    """A class to represent the Rydberg model potential.

    All parameters and potentials are in atomic units.
    """

    species: str
    n: int
    l: int
    s: Union[int, float]
    j: Union[int, float]
    add_spin_orbit: bool = True
    add_model_potentials: bool = True
    db_path: Optional[str] = None
    database: Optional[Database] = None
    use_numepr: bool = False

    def __post_init__(self) -> None:
        """Load the model potential and Rydberg-Ritz parameters from the Database.

        For more details see `database.Database`.
        """
        if self.database is not None and self.db_path is not None:
            raise ValueError("You cannot specify both a database and a database path.")

        if self.database is None:
            self.database = Database(self.db_path)

        self.model_params = self.database.get_model_potential(self.species, self.l)
        self.ritz_params = self.database.get_rydberg_ritz(self.species, self.l, self.j)

        self.ground_state = self.database.get_ground_state(self.species)
        if not self.ground_state.is_allowed_shell(self.n, self.l):
            raise InvalidStateError(
                f"The shell (n={self.n=}, l={self.l}) is not allowed for the species {self.species}."
            )

    @property
    def n_star(self) -> float:
        params = self.ritz_params
        delta_nlj = (
            params.d0
            + params.d2 / (self.n - params.d0) ** 2
            + params.d4 / (self.n - params.d0) ** 4
            + params.d6 / (self.n - params.d0) ** 6
        )
        return self.n - delta_nlj

    @property
    def energy(self) -> float:
        r"""Return the energy of a Rydberg state with principal quantum number n in atomic units.

        The effective principal quantum number in quantum defect theory is defined as series expansion

        .. math::
            n^* = n - \\delta_{nlj}

        where

        .. math::
            \\delta_{nlj} = d_{0} + \frac{d_{2}}{(n - d_{0})^2}
            + \frac{d_{4}}{(n - d_{0})^4} + \frac{d_{6}}{(n - d_{0})^6}

        is the quantum defect. The energy of the Rydberg state is then given by

        .. math::
            E_{nlj} / E_H = -\frac{1}{2} \frac{Ry}{Ry_\infty} \frac{1}{n^*}

        where :math:`E_H` is the Hartree energy (the atomic unit of energy).

        Args:
            n: Principal quantum number of the state to calculate the energy for.

        Returns:
            Energy of the Rydberg state in atomic units.

        """
        params = self.ritz_params
        E_nlj = -0.5 * params.mu / self.n_star**2
        return E_nlj

    def calc_V_c(self, x: np.ndarray) -> np.ndarray:
        r"""Calculate the core potential V_c(x) in atomic units.

        The core potential is given as

        .. math::
            V_c(x) = -Z_{nl} / x

        where x = r / a_0 and Z_{nl} is the effective nuclear charge

        .. math::
            Z_{nl} = 1 + (Z - 1) \exp(-a_1 x) - x (a_3 + a_4 x) \exp(-a_2 x)

        Args:
            x: The dimensionless radial coordinate x = r / a_0, for which to calculate potential.

        Returns:
            V_c: The core potential V_c(x) in atomic units.

        """
        if not self.add_model_potentials:
            return -1 / x
        params = self.model_params
        if self.use_numepr:
            a1, a2 = params.a1, params.a2  # noqa: F841
            exp_a1 = ne.evaluate("exp(-a1 * x)")
            exp_a2 = ne.evaluate("exp(-a2 * x)")
        else:
            exp_a1 = np.exp(-params.a1 * x)
            exp_a2 = np.exp(-params.a2 * x)
        Z_nl = 1 + (params.Z - 1) * exp_a1 - x * (params.a3 + params.a4 * x) * exp_a2
        V_c = -Z_nl / x
        return V_c

    def calc_V_p(self, x: np.ndarray) -> np.ndarray:
        r"""Calculate the core polarization potential V_p(x) in atomic units.

        The core polarization potential is given as

        .. math::
            V_p(x) = -\frac{a_c}{2x^4} (1 - e^{-x^6/x_c**6})

        where x = r / a_0, a_c is the static core dipole polarizability and x_c is the effective core size.

        Args:
            x: The dimensionless radial coordinate x = r / a_0, for which to calculate potential.

        Returns:
            V_p: The polarization potential V_p(x) in atomic units.

        """
        params = self.model_params
        if params.ac == 0 or not self.add_model_potentials:
            return np.zeros_like(x)
        x2 = x * x
        x4 = x2 * x2
        x6 = x4 * x2
        if self.use_numepr:
            xc = params.xc  # noqa: F841
            exp_x6 = ne.evaluate("exp(-(x6 / xc**6))")
        else:
            exp_x6 = np.exp(-(x6 / params.xc**6))
        V_p = -params.ac / (2 * x4) * (1 - exp_x6)
        return V_p

    def calc_V_so(self, x: np.ndarray) -> np.ndarray:
        r"""Calculate the spin-orbit coupling potential V_so(x) in atomic units.

        The spin-orbit coupling potential is given as

        .. math::
            V_{so}(x > x_c) = \frac{\alpha^2}{4x^3} [j(j+1) - l(l+1) - s(s+1)]

        where x = r / a_0, \alpha is the fine structure constant,
        j is the total angular momentum quantum number, l is the orbital angular momentum
        quantum number, and s is the spin quantum number.

        Args:
            x: The dimensionless radial coordinate x = r / a_0, for which to calculate potential.

        Returns:
            V_so: The spin-orbit coupling potential V_so(x) in atomic units.

        """
        alpha = ureg.Quantity(1, "fine_structure_constant").to_base_units().magnitude
        x3 = x * x * x
        V_so = alpha**2 / (4 * x3) * (self.j * (self.j + 1) - self.l * (self.l + 1) - self.s * (self.s + 1))
        if x[0] < self.model_params.xc:
            V_so *= x > self.model_params.xc
        return V_so

    def calc_V_l(self, x: np.ndarray) -> np.ndarray:
        r"""Calculate the centrifugal potential V_l(x) in atomic units.

        The centrifugal potential is given as

        .. math::
            V_l(x) = \frac{l(l+1)}{2x^2}

        where x = r / a_0 and l is the orbital angular momentum quantum number.

        Args:
            x: The dimensionless radial coordinate x = r / a_0, for which to calculate potential.

        Returns:
            V_l: The centrifugal potential V_l(x) in atomic units.

        """
        x2 = x * x
        V_l = (1 / self.ritz_params.mu) * self.l * (self.l + 1) / (2 * x2)
        return V_l

    def calc_V_sqrt(self, x: np.ndarray) -> np.ndarray:
        r"""Calculate the effective potential V_sqrt(x) from the sqrt transformation in atomic units.

        The sqrt transformation potential arises from the transformation from the wavefunction u(x) to w(z),
        where x = r / a_0 and w(z) = z^{-1/2} u(x=z^2) = (r/a_0)^{-1/4} sqrt(a_0) r R(r).
        Due to the transformation, an additional term is added to the radial Schrödinger equation,
        which can be written as effective potential V_{sqrt}(x) and is given by

        .. math::
            V_{sqrt}(x) = \frac{3}{32x^2}

        Args:
            x: The dimensionless radial coordinate x = r / a_0, for which to calculate potential.

        Returns:
            V_sqrt: The sqrt transformation potential V_sqrt(x) in atomic units.

        """
        x2 = x * x
        V_sqrt = (1 / self.ritz_params.mu) * (3 / 32) / x2
        return V_sqrt

    def calc_V_phys(self, x: np.ndarray) -> np.ndarray:
        r"""Calculate the total physical potential V_phys(x) in atomic units.

        The total physical potential is the sum of the core potential, polarization potential,
        centrifugal potential, and optionally the spin-orbit coupling:

        .. math::
            V_{phys}(x) = V_c(x) + V_p(x) + V_l(x) + V_{so}(x)

        Args:
            x: The dimensionless radial coordinate x = r / a_0, for which to calculate potential.

        Returns:
            V_phys: The total physical potential V_phys(x) in atomic units.

        """
        V_tot = self.calc_V_c(x) + self.calc_V_p(x) + self.calc_V_l(x)
        if self.add_spin_orbit:
            V_tot += self.calc_V_so(x)
        return V_tot

    def calc_V_tot(self, x: np.ndarray) -> np.ndarray:
        r"""Calculate the total potential V_tot(x) in atomic units.

        The total effective potential includes all physical and non-physical potentials:

        .. math::
            V_{tot}(x) = V_c(x) + V_p(x) + V_l(x) + V_{so}(x) + V_{sqrt}(x)

        Args:
            x: The dimensionless radial coordinate x = r / a_0, for which to calculate potential.

        Returns:
            V_tot: The total potential V_tot(x) in atomic units.

        """
        V_tot = self.calc_V_phys(x) + self.calc_V_sqrt(x)
        return V_tot

    def calc_z_turning_point(self, which: Literal["hydrogen", "classical", "zerocrossing"], dz: float = 1e-3) -> float:
        r"""Calculate the inner turning point z_i for the model potential.

        There are three different turning points we consider:
        - The hydrogen turning point, where for the idealized hydrogen atom the potential equals the energy,
        i.e. V_c(r_i) + V_l(r_i) = E.
        This is exactly the case at

        .. math::
            r_i = n^2 - n \sqrt{n^2 - l(l + 1)}

        - The classical turning point, where the physical potential of the Rydberg model potential equals the energy,
        i.e. V_phys(r_i) = V_c(r_i) + V_p(r_i) + V_l(r_i) + V_{so}(r_i) = E.

        - The zero-crossing turning point, where the physical potential of the Rydberg model potential equals zero,
        i.e. V_phys(r_i) = V_c(r_i) + V_p(r_i) + V_l(r_i) + V_{so}(r_i) = 0.

        Args:
            which: Which turning point to calculate, one of "hydrogen", "classical", "zerocrossing".
            dz: The precision of the turning point calculation.

        Returns:
            z_i: The inner turning point z_i in the scaled dimensionless coordinate z_i = sqrt{r_i / a_0}.

        """
        assert which in ["hydrogen", "classical", "zerocrossing"], f"Invalid turning point method {which}."
        hydrogen_r_i = self.n * self.n - self.n * np.sqrt(self.n * self.n - self.l * (self.l - 1))
        hydrogen_z_i = np.sqrt(hydrogen_r_i)

        if which == "hydrogen":
            return hydrogen_z_i

        zlist = np.arange(max(dz, hydrogen_z_i - 10), max(hydrogen_z_i + 10, 10), dz)
        xlist = zlist * zlist
        V_phys = self.calc_V_phys(xlist)

        if which == "classical":
            arg = np.argwhere(V_phys < self.energy)[0][0]
        else:  # "zerocrossing"
            arg = np.argwhere(V_phys < 0)[0][0]

        if arg == 0:
            if self.l == 0:
                return 0
            logger.warning("Turning point is at arg=0, this shouldnt happen.")
        elif arg == len(zlist) - 1:
            logger.warning("Turning point is at maixmal arg, this shouldnt happen.")

        return zlist[arg]
