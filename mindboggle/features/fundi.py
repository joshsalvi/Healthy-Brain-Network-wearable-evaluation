#!/usr/bin/env python
"""
Extract fundus curves from surface mesh patches (folds).

Authors:
Arno Klein, 2013-2016  .  arno@mindboggle.info  .  www.binarybottle.com

Copyright 2016,  Mindboggle team (http://mindboggle.info), Apache v2.0 License

"""


def extract_fundi(folds, curv_file, depth_file, min_separation=10,
                  erode_ratio=0.1, erode_min_size=1, save_file=False,
                  background_value=-1, verbose=False):
    """
    Extract fundi from folds.

    A fundus is a branching curve that runs along the deepest and most
    highly curved portions of a fold.

    Steps ::
        1. Find fundus endpoints (outer anchors) with find_outer_endpoints().
        2. Include inner anchor points.
        3. Connect anchor points using connect_points_erosion();
           inner anchors are removed if they result in endpoints.

    Parameters
    ----------
    folds : numpy array or list of integers
        fold number for each vertex
    curv_file :  string
        surface mesh file in VTK format with mean curvature values
    depth_file :  string
        surface mesh file in VTK format with rescaled depth values
    likelihoods : list of integers
        fundus likelihood value for each vertex
    min_separation : integer
        minimum number of edges between inner/outer anchor points
    erode_ratio : float
        fraction of indices to test for removal at each iteration
        in connect_points_erosion()
    save_file : bool
        save output VTK file?
    background_value : integer or float
        background value
    verbose : bool
        print statements?

    Returns
    -------
    fundus_per_fold : list of integers
        fundus numbers for all vertices, labeled by fold
        (-1 for non-fundus vertices)
    n_fundi_in_folds :  integer
        number of fundi
    fundus_per_fold_file : string (if save_file)
        output VTK file with fundus numbers (-1 for non-fundus vertices)

    Examples
    --------
    >>> # Extract fundus from one or more folds:
    >>> import numpy as np
    >>> from mindboggle.mio.vtks import read_scalars
    >>> from mindboggle.features.fundi import extract_fundi
    >>> from mindboggle.mio.fetch_data import prep_tests
    >>> urls, fetch_data = prep_tests()
    >>> curv_file = fetch_data(urls['left_mean_curvature'])
    >>> depth_file = fetch_data(urls['left_travel_depth'])
    >>> folds_file = fetch_data(urls['left_folds'])
    >>> folds, name = read_scalars(folds_file, True, True)
    >>> # Limit number of folds to speed up the test:
    >>> limit_folds = False #True
    >>> if limit_folds:
    ...     fold_numbers = [4] #[4, 6]
    ...     i0 = [i for i,x in enumerate(folds) if x not in fold_numbers]
    ...     folds[i0] = -1
    >>> min_separation = 10
    >>> erode_ratio = 0.10
    >>> erode_min_size = 10
    >>> save_file = True
    >>> background_value = -1
    >>> verbose = False
    >>> o1, o2, fundus_per_fold_file = extract_fundi(folds, curv_file,
    ...     depth_file, min_separation, erode_ratio, erode_min_size,
    ...     save_file, background_value, verbose)
    >>> lens = [len([x for x in o1 if x == y])
    ...         for y in np.unique(o1) if y != -1]
    >>> lens[0:10] # [66, 2914, 100, 363, 73, 331, 59, 30, 1, 14]
    [2207, 187, 1, 29, 1, 176, 1, 1, 9, 1]
    [73]

    View result (skip test):

    >>> from mindboggle.mio.plots import plot_surfaces # doctest: +SKIP
    >>> plot_surfaces(fundus_per_fold_file) # doctest: +SKIP

    """

    # Extract a skeleton to connect endpoints in a fold:
    import os
    import numpy as np
    from time import time

    from mindboggle.mio.vtks import read_scalars, read_vtk, rewrite_scalars
    from mindboggle.guts.compute import median_abs_dev
    from mindboggle.guts.paths import find_max_values
    from mindboggle.guts.mesh import find_neighbors_from_file
    from mindboggle.guts.mesh import find_complete_faces
    from mindboggle.guts.paths import find_outer_endpoints
    from mindboggle.guts.paths import connect_points_erosion

    if isinstance(folds, list):
        folds = np.array(folds)

    # Load values, inner anchor threshold, and neighbors:
    if os.path.isfile(curv_file):
        points, indices, lines, faces, curvs, scalar_names, npoints, \
            input_vtk = read_vtk(curv_file, True, True)
    else:
        raise(IOError("{0} doesn't exist!".format(curv_file)))
    if os.path.isfile(curv_file):
        depths, name = read_scalars(depth_file, True, True)
    else:
        raise(IOError("{0} doesn't exist!".format(depth_file)))
    values = curvs * depths
    values0 = [x for x in values if x > 0]
    thr = np.median(values0) + 2 * median_abs_dev(values0)
    neighbor_lists = find_neighbors_from_file(curv_file)

    #-------------------------------------------------------------------------
    # Loop through folds:
    #-------------------------------------------------------------------------
    t1 = time()
    skeletons = []
    unique_fold_IDs = [x for x in np.unique(folds) if x != background_value]

    if verbose:
        if len(unique_fold_IDs) == 1:
            print("Extract a fundus from 1 fold...")
        else:
            print("Extract a fundus from each of {0} folds...".
                  format(len(unique_fold_IDs)))

    for fold_ID in unique_fold_IDs:
        indices_fold = [i for i,x in enumerate(folds) if x == fold_ID]
        if indices_fold:
            if verbose:
                print('  Fold {0}:'.format(int(fold_ID)))

            #-----------------------------------------------------------------
            # Find outer anchor points on the boundary of the surface region,
            # to serve as fundus endpoints:
            #-----------------------------------------------------------------
            verbose = False
            outer_anchors, tracks = find_outer_endpoints(indices_fold,
                neighbor_lists, values, depths, min_separation, verbose)

            #-----------------------------------------------------------------
            # Find inner anchor points:
            #-----------------------------------------------------------------
            inner_anchors = find_max_values(points, values, min_separation,
                                            thr)

            #-----------------------------------------------------------------
            # Connect anchor points to create skeleton:
            #-----------------------------------------------------------------
            B = background_value * np.ones(npoints)
            B[indices_fold] = 1
            skeleton = connect_points_erosion(B, neighbor_lists,
                outer_anchors, inner_anchors, values, erode_ratio,
                erode_min_size, [], '', background_value, verbose)
            if skeleton:
                skeletons.extend(skeleton)

            #-----------------------------------------------------------------
            # Remove fundus vertices if they complete triangle faces:
            #-----------------------------------------------------------------
            Iremove = find_complete_faces(skeletons, faces)
            if Iremove:
                skeletons = list(frozenset(skeletons).difference(Iremove))

    indices_skel = [x for x in skeletons if folds[x] != background_value]
    fundus_per_fold = background_value * np.ones(npoints)
    fundus_per_fold[indices_skel] = folds[indices_skel]
    n_fundi_in_folds = len([x for x in np.unique(fundus_per_fold)
                             if x != background_value])
    if n_fundi_in_folds == 1:
        sdum = 'fold fundus'
    else:
        sdum = 'fold fundi'
    if verbose:
        print('  ...Extracted {0} {1}; {2} total ({3:.2f} seconds)'.
              format(n_fundi_in_folds, sdum, n_fundi_in_folds, time() - t1))

    #-------------------------------------------------------------------------
    # Return fundi, number of fundi, and file name:
    #-------------------------------------------------------------------------
    fundus_per_fold_file = None
    if n_fundi_in_folds > 0:
        fundus_per_fold = [int(x) for x in fundus_per_fold]
        if save_file:
            fundus_per_fold_file = os.path.join(os.getcwd(),
                                                'fundus_per_fold.vtk')
            rewrite_scalars(curv_file, fundus_per_fold_file, fundus_per_fold,
                            'fundi', [], background_value)
            if not os.path.exists(fundus_per_fold_file):
                raise IOError(fundus_per_fold_file + " not found")

    return fundus_per_fold,  n_fundi_in_folds, fundus_per_fold_file


def segment_fundi(fundus_per_fold, sulci=[], vtk_file='', save_file=False,
                  background_value=-1, verbose=False):
    """
    Segment fundi by sulcus definitions.

    Parameters
    ----------
    fundus_per_fold : list of integers
        fundus numbers for all vertices, labeled by fold
        (-1 for non-fundus vertices)
    sulci : numpy array or list of integers
        sulcus number for each vertex, used to filter and label fundi
    vtk_file : string (if save_file)
        VTK file with sulcus number for each vertex
    save_file : bool
        save output VTK file?
    background_value : integer or float
        background value
    verbose : bool
        print statements?

    Returns
    -------
    fundus_per_sulcus : list of integers
        fundus numbers for all vertices, labeled by sulcus
        (-1 for non-fundus vertices)
    n_fundi :  integer
        number of fundi
    fundus_per_sulcus_file : string (if save_file)
        output VTK file with fundus numbers (-1 for non-fundus vertices)

    Examples
    --------
    >>> # Segment fundi by sulci:
    >>> import numpy as np
#    >>> single_fold = True
    >>> from mindboggle.features.fundi import segment_fundi
#    >>> from mindboggle.features.fundi import extract_fundi
    >>> from mindboggle.mio.vtks import read_scalars
    >>> from mindboggle.mio.fetch_data import prep_tests
    >>> urls, fetch_data = prep_tests()
#    >>> curv_file = fetch_data(urls['left_mean_curvature'])
#    >>> depth_file = fetch_data(urls['left_travel_depth'])
    >>> fundus_file = fetch_data(urls['left_fundi'])
    >>> vtk_file = fetch_data(urls['left_sulci'])
    >>> sulci = read_scalars(vtk_file, True, True)
    >>> fundus_per_fold, name = read_scalars(fundus_file, True, True)
    # >>> folds, name = read_scalars(folds_file, True, True)
    # >>> # Limit number of folds to speed up the test:
    # >>> limit_folds = True
    # >>> if limit_folds:
    # ...     fold_numbers = [4] #[4, 6]
    # ...     i0 = [i for i,x in enumerate(folds) if x not in fold_numbers]
    # ...     folds[i0] = -1
    # >>> min_separation = 10
    # >>> erode_ratio = 0.10
    # >>> erode_min_size = 10
    >>> save_file = True
    >>> background_value = -1
    >>> verbose = False
    # >>> fundus_per_fold, o1, o2 = extract_fundi(folds,
    # ...     curv_file, depth_file, min_separation, erode_ratio,
    # ...     erode_min_size, save_file, background_value, verbose)

    >>> o1, o2, fundus_per_sulcus_file = segment_fundi(fundus_per_fold,
    ...     sulci, vtk_file, save_file, background_value, verbose)
    >>> segment_numbers = [x for x in np.unique(o1) if x != -1]
    >>> lens = []
    >>> for segment_number in segment_numbers:
    ...     lens.append(len([x for x in o1 if x == segment_number]))
    >>> lens
    [73]

    View result (skip test):

    >>> from mindboggle.mio.plots import plot_surfaces
    >>> plot_surfaces(fundus_per_sulcus_file) # doctest: +SKIP

    """

    # Extract a skeleton to connect endpoints in a fold:
    import os
    import numpy as np

    from mindboggle.mio.vtks import rewrite_scalars

    if isinstance(sulci, list):
        sulci = np.array(sulci)

    #-------------------------------------------------------------------------
    # Create fundi by segmenting fold fundi with overlapping sulcus labels:
    #-------------------------------------------------------------------------
    indices = [i for i,x in enumerate(fundus_per_fold)
               if x != background_value]
    if indices and np.size(sulci):
        fundus_per_sulcus = background_value * np.ones(len(sulci))
        fundus_per_sulcus[indices] = sulci[indices]
        n_fundi = len([x for x in np.unique(fundus_per_sulcus)
                       if x != background_value])
    else:
        fundus_per_sulcus = []
        n_fundi = 0

    if n_fundi == 1:
        sdum = 'sulcus fundus'
    else:
        sdum = 'sulcus fundi'
    if verbose:
        print('  Segmented {0} {1}'.format(n_fundi, sdum))

    #-------------------------------------------------------------------------
    # Return fundi, number of fundi, and file name:
    #-------------------------------------------------------------------------
    fundus_per_sulcus_file = None
    if n_fundi > 0:
        fundus_per_sulcus = [int(x) for x in fundus_per_sulcus]
        if save_file and os.path.exists(vtk_file):
            fundus_per_sulcus_file = os.path.join(os.getcwd(),
                                                  'fundus_per_sulcus.vtk')
            # Do not filter faces/points by scalars when saving file:
            rewrite_scalars(vtk_file, fundus_per_sulcus_file,
                            fundus_per_sulcus, 'fundus_per_sulcus', [],
                            background_value)
            if not os.path.exists(fundus_per_sulcus_file):
                raise IOError(fundus_per_sulcus_file + " not found")

    return fundus_per_sulcus, n_fundi, fundus_per_sulcus_file

#=============================================================================
# Doctests
#=============================================================================
if __name__ == "__main__":
    import doctest
    doctest.testmod(verbose=True)  # py.test --doctest-modules