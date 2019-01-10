from pymatgen.core.structure import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.core.periodic_table import Element, Specie
import numpy as np
from angular_momentum import CG, wigner_D
from optparse import OptionParser
from numba import jit


@jit
def _cutoff_function(r, rc):

    if r > rc:
        return 0.

    else:
        return 0.5 * (np.cos(np.pi * r / rc) + 1.)


class Bispectrum(object):

    @jit(parallel=True)
    def __init__(self, crystal, j_max=5, cutoff_radius=6.5, symmetrize=True):
        '''
        '''

        # populate private attributes
        self._j_max = j_max
        self._Rc = cutoff_radius

        self._factorial = [1]

        # symmetrize structure option
        if symmetrize:
            finder = SpacegroupAnalyzer(crystal, symprec=0.06,
                                        angle_tolerance=5)
            crystal = finder.get_conventional_standard_structure()

        '''
        Here we iterate over each site and its corresponding neighbor
        environment to compute the bispectrum coefficients of each
        site-neighbor interaction.

        At each site, the bispectrum is a list where the list elements are
        the bispectrum corresponds each to a site-neighbor interaction

        In turn the descriptor is effectively a list of lists, where the
        element lists contain the bispectrum coefficients of the neighbor
        environment
        '''
        self.bispectrum = []
        neighbors = crystal.get_all_neighbors(self._Rc)
        for index, site in enumerate(crystal):
            site_neighbors = neighbors[index]
            # site loops over central atoms
            site_bispectrum = []
            # iterate over 2*j_max
            for _2j1 in range(2 * self._j_max + 1):
                j1, j2 = _2j1/2, _2j1/2
                # iterate over j_max -1
                for j in range(int(min(_2j1, self._j_max,)) + 1):
                    # calculate the real terms of the bispectrums
                    term = self._calculate_B(
                        j1, j2, 1.0*j, site, site_neighbors)
                    term = term.real
                    site_bispectrum += [term]
            self.bispectrum += [site_bispectrum]

    @staticmethod
    def _m_values(k):
        return np.arange(-k, k+1, 1)

    @jit(parallel=True)
    def _calculate_B(self, j1, j2, j, site, site_neighbors):
        '''
        Calculates the bispectrum coefficients associated with
        atomic site in a crystal structure

        Args:
            j1: index for first summnation
            j2: index for second summnation
            j: index of spherical harmonic expansion
            site: pymatgen site for central atom
            site_neighbors: pymatgen site neighbor list
                corresponding to the central atom

        Returns:
            Bispectrum coefficients: a list of floats
        '''
        # itiate the variable
        B = 0.
        # compute the set of free integer parameters
        mvals = self._m_values(j)
        # iterate over two free integer sets
        for m in mvals:
            for m_prime in mvals:
                # see calculate c
                c = self._calculate_c(j, m_prime, m, site, site_neighbors)
                # assign new integer parameters, related to m and m prime
                m1bound = min(j1, m + j2)
                m_prime1_bound = min(j1, m_prime + j2)
                m1 = max(-j1, m-j2)
                '''
                Iterate over a set of half integer values depending on the free
                integer parameters m and m_prime
                '''
                while m1 < (m1bound + 0.5):
                    m_prime1 = max(-j1, m_prime - j2)
                    while m_prime1 < (m_prime1_bound + 0.5):
                        c1 = self._calculate_c(j1, m_prime1, m1, site,
                                               site_neighbors)
                        c2 = self._calculate_c(j2, m_prime-m_prime1, m-m1, site,
                                               site_neighbors)

                        B += float(CG(j1, m1, j2, m-m1, j, m)) * \
                            float(CG(j1, m_prime1, j2, m_prime-m_prime1, j, m_prime)) * \
                            np.conjugate(c) * c1 * c2
                        m_prime1 += 1
                    m1 += 1

        return B

    @jit(parallel=True)
    def _calculate_c(self, j, m_prime, m, site, site_neighbors):
        '''
        Calculate the inner product of the 4-D spherical harmonics associated
        with an atomic site and integer/half-integer parameters

        Args:
            j, m_prime, m:  integer/half-integer parameters
            site: a pymatgen periodic site object
            site_neighbors: a list of pymatgen periodic site
                            objects corresponding to the sites
                            nearest neighbors

        Returns:  the inner product of the harmonics associated with each neighbor
        '''
        # ititiate the data as a float
        dot = 0.
        '''
        Calculate the 4-D spherical harmonic assoicated with each neigjbor/site pair
        and add it to value to compute the inner product
        '''
        for neighbor in site_neighbors:
            '''
            Calculate x, y, z, and the magnitude of the position vector
            by calling the cartesian coordinates of the pymatgen
            periodic site objects,  index 0 corresponds to x, 1 to y, and
            2 to z
            '''
            x = neighbor[0].coords[0] - site.coords[0]
            y = neighbor[0].coords[1] - site.coords[1]
            z = neighbor[0].coords[2] - site.coords[2]
            r = neighbor[1]  # distance is stored here
            ele = neighbor[0].specie
            G = ele.number
            '''
            If the magnitude of the position vector is approximately greater
            than zero compute the 4-D spherical harmonic associated with that site
            if not continue.
            '''
            if r > 10.**(-10.):
                # first euler rotation angle
                psi = np.arcsin(r / self._Rc)

                '''
                Second euler rotation angle, corresponds to the polar angle in
                3-D spherical coordinates
                '''
                theta = np.arccos(z / r)
                if abs((z / r) - 1.0) < 10.**(-8.):
                    theta = 0.0
                elif abs((z / r) + 1.0) < 10.**(-8.):
                    theta = np.pi

                '''
                Third euler rotation angle, corresponds to the azimuthal angle in
                3-D spherical coordinates
                '''
                if x < 0.:
                    phi = np.pi + np.arctan(y / x)
                elif 0. < x and y < 0.:
                    phi = 2 * np.pi + np.arctan(y / x)
                elif 0. < x and 0. <= y:
                    phi = np.arctan(y / x)
                elif x == 0. and 0. < y:
                    phi = 0.5 * np.pi
                elif x == 0. and y < 0.:
                    phi = 1.5 * np.pi
                else:
                    phi = 0.

                '''
                add the spherical harmonic multiplied by the cutoff function to the
                inner product, the vectors considered are the complex numbers
                associated with the spherical harmonic, the conjugate is the
                scalar product
                '''
                dot += G * \
                    np.conjugate(self._U(j, m, m_prime, psi, theta, phi)) * \
                    _cutoff_function(r, self._Rc)

            else:
                continue

        return dot

    @jit(parallel=True)
    def _U(self, j, m, m_prime, psi, theta, phi):
        '''
        Computes an element of the rotation group SO3
        corresponding to integer / half integer values
        j, m and m prime along with rotation angles psi,
        theta, and phi

        These elements are also the 4-D spherical harmonics

        Args:
            j: free integer parameter
            m: fixed integer/half=integer parameter
            m_prime: fixed integer/half-integer parameter
            psi, theta, phi:  euler angles

        Returns:  an element of the rotation group SO3, complex
        '''
        sph_harm = 0. + 0.j
        mvals = self._m_values(j)
        for mp in mvals:
            sph_harm += wigner_D(j, m, mp, phi, theta, -phi) * \
                np.exp(-1j * mp * psi) * \
                wigner_D(j, mp, m_prime, phi, -theta, -phi)

        return sph_harm


if __name__ == "__main__":
    # ---------------------- Options ------------------------
    parser = OptionParser()
    parser.add_option("-c", "--crystal", dest="structure", default='',
                      help="crystal from file, cif or poscar, REQUIRED",
                      metavar="crystal")

    (options, args) = parser.parse_args()
    if options.structure.find('cif') > 0:
        fileformat = 'cif'
    else:
        fileformat = 'poscar'

    test = Structure.from_file(options.structure)

    f = Bispectrum(test, j_max=1, cutoff_radius=6.5)
    print(f.bispectrum)
