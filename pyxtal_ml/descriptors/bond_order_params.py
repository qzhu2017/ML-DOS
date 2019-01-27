import numpy as np
from itertools import product
from pyxtal_ml.descriptors.angular_momentum import wigner_3j
from pymatgen.core.structure import Structure
from pymatgen.analysis.local_env import get_neighbors_of_site_with_index
from scipy.special import sph_harm
from pyxtal_ml.descriptors.stats import descriptor_stats
from optparse import OptionParser

def _qlm(site, neighbors, l, mvals):
    '''
       Calculates the complex vector associated with an atomic site and
        one of its neighbors
       Args:
           site: a pymatgen crystal site
            neighbors: a neighbor list corresponding to the site
           l:  free integer parameter
           mvals:  list of free integer parameters
        Returns:
            q: numpy array(complex128), the complex vector qlm normalized
               by the number of nearest neighbors
        '''
    # initiate variable as a complex number
    q = np.zeros(2*l+1, dtype=np.complex128)
    # iterate over mvals
    for i, m in enumerate(mvals):
        # take the neighbor count
        neighbors_count = len(neighbors)
        # iterate over neighbors
        for neighbor in neighbors:
            # find the position vector of the site/neighbor pair
            r_vec = neighbor.coords - site.coords
            r_mag = np.linalg.norm(r_vec)
            # arccos(z/norm(r))
            theta = np.arccos(r_vec[2] / r_mag)
            if abs((r_vec[2] / r_mag) - 1.0) < 10.**(-8.):
                theta = 0.0
            elif abs((r_vec[2] / r_mag) + 1.0) < 10.**(-8.):
                theta = np.pi

            # phi
            if r_vec[0] < 0.:
                phi = np.pi + np.arctan(r_vec[1] / r_vec[0])
            elif 0. < r_vec[0] and r_vec[1] < 0.:
                phi = 2 * np.pi + np.arctan(r_vec[1] / r_vec[0])
            elif 0. < r_vec[0] and 0. <= r_vec[1]:
                phi = np.arctan(r_vec[1] / r_vec[0])
            elif r_vec[0] == 0. and 0. < r_vec[1]:
                phi = 0.5 * np.pi
            elif r_vec[0] == 0. and r_vec[1] < 0.:
                phi = 1.5 * np.pi
            else:
                phi = 0.
            '''
            calculate the spherical harmonic associated with
            the neighbor and add to q
            '''
            q[i] += sph_harm(m, l, phi, theta)
    # normalize by number of neighbors
    return q / neighbors_count

def _scalar_product(q1, q2):
    '''
    Calculates the scalar product between two
    complex vectors using the conjugate
    Args:
        q1: a complex vector
        q2: a complex vector
    Returns:  float, The scalar product of two complex vectors
    '''

    '''
    take the scalar product (vector * conjugates) and sum them
    to calculate the scalar product, this will be a real number
    so change the data type to float
    '''
    return float(np.sum(q1*np.conjugate(q2)))

def _ql(scalar_product, l):
    '''
    Calculates the steinhardt bond order parameter ql
    given the scalar product of the complex vector of qlms with itself
    and the parameter degree l
    Args:
        scalar_product: the scalar product of the complex vector qli
                        with itself
        l: the degree of the bond order parameter
    Returns:
        ql:  float, the steinhardt bond order parameter ql
    '''
    constant = (4 * np.pi) / (2*l + 1)
    return np.sqrt(constant * scalar_product)


def _wli(qlms, l, m1, m2, m3):
    '''Calculates the steinhardt bond order parameter wl
       given the complex vector qlms, the parameter degree l
        and the free integer parameters m1, m2, and m3
       Args:
           qlms:  the complex vector of qlm values
                    corresponding to the parameter degree
            l:  degree of the steinhardt bond order parameter
           m1, m2, m3:  free integer parameters
       Returns:
            wli: float, the real part of the complex steinhardt bond order
                parameter wl
    '''
    # calculate the wigner3j value for l and the free integer parameters (float)
    w3j = wigner_3j(l, m1-l, l, m2-l, l, m3-l)
    '''
    call the complex numbers with indeces corresponding to the free
    integer parameters m1, m2, m3 and multiply them together
    '''
    q1 = qlms[m1]
    q2 = qlms[m2]
    q3 = qlms[m3]
    q = q1 * q2 * q3
    # multiply the wigner3j value and the real part of the product of q1, q2, q3
    wli = w3j * q.real
    return wli

class steinhardt_params(object):
    '''
    Computes the steinhardt bond order parameters corresponding to each
    periodic site in a Pymatgen crystal structure

    Args:
        crystal:  A pymatgen crystal structure
        L: maximum degree of order parameter
    '''
    def __init__(self, crystal, L=6):
        # all bond order parameters up to maximum degree L
        Ls = np.arange(2, L+1, 1)
        '''populate a dictionary of empty lists with keys corresponding
           to each bond order parameter up to L'''
        bond_order_params = self._populate_dicts(Ls)
        '''loop over l to calculate each bond order parameter
           and store it in the dictionary'''
        for l in Ls:
            # to index the dictionary
            parameter_index = str(l)
            # iterate over each periodic site in the pymatgen crystal structure
            for index, site in enumerate(crystal):
                # get all nearest neighbors
                neighbors = get_neighbors_of_site_with_index(
                    crystal, index, approach='voronoi')
                # generate free integer parameters
                mvals = self._mvalues(l)
                # complex vector of all qlms generated by the free integer parameters
                qlms = _qlm(site, neighbors, l, mvals)
                # scalar product of qlm with itself
                dot = _scalar_product(qlms, qlms)
                # calculate ql see _ql method
                bond_order_params['q' + parameter_index] += [_ql(dot, l)]

                '''
                Here we use a mapping from the free integer parameter set [-l,l]
                to the set [0, 2l] in order to index the complex vector for the
                computation of the wl bond order parameter

                It is more convenient to use the set [0, 2l] to index qlms as
                [0, 2l] is the set of indeces for the array elements

                When m1 + m2 + m3 belonging to the set [-l,l] is 0;
                     m1 + m2 + m3 belonging to the set [0, 2l] is exactly 3 * l
                '''
                # the set [0, 2l]
                iterator = np.arange(0, 2*l+1, 1)
                # initiate wli as a float
                wli = 0.
                # equivalent to a triple for loop
                for m1, m2, m3 in product(iterator, repeat=3):
                    '''
                    This case corresponds to when m1 + m2 + m3 in the set [-l,l]
                    is zero
                    '''
                    if m1 + m2 + m3 == 3 * l:
                        # add wli to the bond order parameter
                        wli += _wli(qlms, l, m1, m2, m3)
                # normalize by the scalar product of the complex vector
                bond_order_params['w' + parameter_index] += [wli/(dot**(3/2))]

        # call the values in the dictionary and insert them into a list
        parameters = list(bond_order_params.values())
        print(np.shape(parameters))
        '''
        If the list is 1 dimensional simply take the mean of the list
        If the list is 2 dimensional take the mean over the rows of the list'''
        try:  # 2D case
            self.params = descriptor_stats(parameters, axis=1).get_stats()
        except:  # 1D case
            self.params = descriptor_stats(parameters).get_stats()

    @staticmethod
    def _mvalues(l):
        '''Returns the closed set of integers [-l,l]'''
        return np.arange(-l, l+1, 1)

    def _populate_dicts(self, ls):
        '''
        Populates a dictionary for all steinhardt order parameters
        q0, w0, q1, w1 , ... , ql, ql
        '''
        parameter_dict = {}
        for l in ls:
            index = str(l)
            parameter_dict['q' + index] = []
            parameter_dict['w' + index] = []
        return parameter_dict


if __name__ == '__main__':
    # ------------------------ Options -------------------------------------
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
    print(steinhardt_params(test, 12).params)
