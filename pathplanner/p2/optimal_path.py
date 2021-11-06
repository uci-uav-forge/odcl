import matplotlib.pyplot as plt
from matplotlib import cm
import numpy as np
import networkx as nx
import cvxpy as cp
from collections import defaultdict
from scipy.spatial import distance
from mpl_toolkits.mplot3d.axes3d import Axes3D


def astar(X, Y, H, start, goal, dist_heur="euclidean", heur_cost=0.1):
    """Astar function

    `X`, `Y`, `H` are 2d arrays indicating x, y, h scalars. `start`, `goal` are
    tuples; they are the index of a start point and an end point in those `X`, `Y`
    arrays.

    dist_heur is a string that can take values `"euclidean"`, `"least_diff"`, or `"lowest"`
    to generate the euclidean path in R3, the pairwise least diff path, or the lowest path,
    respectively.

    `heur_cost` is not required for `"euclidean"`, but is required for `"least_diff"` and
    `"lowest"` paths. It corresponds to the cost that should be added to the R2 euclidean
    distance when using those heuristics.
    """

    def yield_neighbors(ij):
        ij = np.array(ij)
        xmax = np.array(X.shape)
        zeros = np.array((0, 0))
        # neighbors
        for n in np.array([[1, 0], [-1, 0], [0, 1], [0, -1]]):
            # edge of wall
            point = ij + n
            edge = np.any(point >= xmax) or np.any(point <= zeros)
            if not edge:
                yield tuple(point)

    def h(ij1, ij2):
        """distance heuristic on indices of X, Y."""
        # R3 distance
        if dist_heur == "euclidean":
            pt1 = np.array((X[tuple(ij1)], Y[tuple(ij1)], H[tuple(ij1)]))
            pt2 = np.array((X[tuple(ij2)], Y[tuple(ij2)], H[tuple(ij2)]))
            d = distance.euclidean(pt1, pt2)
        # R2 distance + height diff between i, j
        elif dist_heur == "least_diff":
            pt1 = np.array((X[tuple(ij1)], Y[tuple(ij1)]))
            pt2 = np.array((X[tuple(ij2)], Y[tuple(ij2)]))
            d = distance.euclidean(pt1, pt2) + heur_cost * np.abs(H[ij1] - H[ij2])
        # R2 distance + absolute height of destination
        elif dist_heur == "lowest":
            pt1 = np.array((X[tuple(ij1)], Y[tuple(ij1)]))
            pt2 = np.array((X[tuple(ij2)], Y[tuple(ij2)]))
            d = distance.euclidean(pt1, pt2) + heur_cost * np.abs(H[ij2])
        return d

    openset = {start}
    came_from = dict()
    gscore = defaultdict(lambda: 1e9)
    gscore[start] = 0

    fscore = defaultdict(lambda: 1e9)
    fscore[start] = h(start, goal)

    while len(openset) != 0:
        current = min(openset, key=lambda v: fscore[v])
        if current == goal:
            return reconstruct_path(came_from, current)
        openset.remove(current)
        for n in yield_neighbors(current):
            tentative_gscore = gscore[current] + h(current, n)
            if tentative_gscore < gscore[n]:
                came_from[n] = current
                gscore[n] = tentative_gscore
                fscore[n] = gscore[n] + h(n, goal)
                if n not in openset:
                    openset.add(n)


def reconstruct_path(predecessors, current):
    """from a map of `predecessors` and a `current` point, trace
    backwards a path from the current point to the origin point"""
    total = [current]
    while current in predecessors:
        current = predecessors[current]
        total.append(current)
    return total


def rand_idx(X):
    """what the heck numpy >:("""
    xidx = list(np.ndindex(X.shape))
    idx_of_rand_xidx = np.random.choice(len(xidx))
    return xidx[idx_of_rand_xidx]


def generate_xy_grid(xrange, yrange, step):
    """make a new xy grid. `xrange` and `yrange` are tuples of (min, max)
    pairs. step is the step size of the grid."""
    # TODO: test heterogenous range values
    xmin, xmax = xrange
    ymin, ymax = yrange
    return np.meshgrid(np.arange(xmin, xmax, step), np.arange(ymin, ymax, step))


def generate_obstacles(n, xrange, yrange, radrange, height_range):
    """generate `n` random cylindrical obstacles and store into a
    list of tuples. each item is the (point, radius, height).
    range is the high/low point of a uniform distribution"""
    obstacles = []
    xmin, xmax = xrange
    ymin, ymax = yrange
    rmin, rmax = radrange
    hmin, hmax = height_range
    for _ in range(n):
        # center
        ocent = np.array([np.random.uniform(xmin, xmax), np.random.uniform(ymin, ymax)])
        # radius
        orad = np.random.uniform(rmin, rmax)
        # height
        oheight = np.random.uniform(hmin, hmax)
        obstacles.append((ocent, orad, oheight))
    return obstacles


def place_obstacles(X, Y, obstacles):
    """make a new grid, H, containing obstacle points.
    points with no obstacles are at 0"""
    H = np.zeros_like(X)
    # check each point
    for ij in np.ndindex(X.shape):
        pt = np.array([X[ij], Y[ij]])
        # against each obstacle
        for ocent, orad, oheight in obstacles:
            if np.dot(pt - ocent, pt - ocent) < orad * orad:
                H[ij] = oheight
    return H


def get_optimal_grid(H, buffer, min_climb, min_acc_climb, min_altitude, verbose=True):
    # new h is a free variable corresponding to H
    newh = cp.Variable(shape=H.shape)
    hc = newh - H >= buffer
    gc = newh >= min_altitude
    # 2nd partial with respect to h -> change in climb rate
    d2xc = cp.abs(cp.diff(newh, 2, axis=0)) <= min_acc_climb
    d2yc = cp.abs(cp.diff(newh, 2, axis=1)) <= min_acc_climb
    # 1st partial with respect to h -> climb rate
    dxc = cp.abs(cp.diff(newh, 1, axis=0)) <= min_climb
    dyc = cp.abs(cp.diff(newh, 1, axis=1)) <= min_climb
    # lowest possible
    cost_fn = cp.sum_squares(newh - H)
    constraints = [hc, gc, d2xc, d2yc, dxc, dyc]
    problem = cp.Problem(cp.Minimize(cost_fn), constraints)
    problem.solve(verbose=verbose, solver="ECOS")
    return newh.value


def set_equal(h, ax):
    """this ensures that the 3d axis `ax` is scaled properly. Distances
    in x and y are equal aspect ratio.

    https://stackoverflow.com/questions/13685386/matplotlib-equal-unit-length-with-equal-aspect-ratio-z-axis-is-not-equal-to"""
    # Create cubic bounding box to simulate equal aspect ratio
    """Fix equal aspect bug for 3D plots."""
    xlim = ax.get_xlim3d()
    ylim = ax.get_ylim3d()
    zlim = ax.get_zlim3d()
    xmean = np.mean(xlim)
    ymean = np.mean(ylim)
    zmean = np.mean(zlim)
    plot_radius = max(
        [
            abs(lim - mean)
            for lims, mean in ((xlim, xmean), (ylim, ymean), (zlim, zmean))
            for lim in lims
        ]
    )
    ax.set_xlim3d([xmean - plot_radius, xmean + plot_radius])
    ax.set_ylim3d([ymean - plot_radius, ymean + plot_radius])
    ax.set_zlim3d([-0.25, np.max(h) + np.max(h) / 10])


def plot_grid(
    fig,
    X,
    Y,
    H,
    Hnew,
    cmap="viridis",
    color_surface="white",
    alpha_surface=0.4,
    ptype="surface",
):
    """Make a plot.

    Parameters
    ----------
    fig : plt.figure
    X : np.ndarray
    Y : np.ndarray
    H : np.ndarray
    Hnew : np.ndarray
    cmap : str, optional
        colormap to use for the "ground", by default "viridis"
    color_surface : str, optional
        color to use for the grid/sheet, by default "white"
    alpha_surface : float, optional
        alpha of the surface, by default 0.4
    ptype : str, optional
        either "surface" or "wireframe" corresponding to one of those two
        plot types, by default "surface"

    Returns
    -------
    ax
        plt.Axis()
    """
    ax = fig.add_subplot(projection="3d")
    # https://stackoverflow.com/questions/30223161/matplotlib-mplot3d-how-to-increase-the-size-of-an-axis-stretch-in-a-3d-plo/30419243#30419243
    ax.get_proj = lambda: np.dot(Axes3D.get_proj(ax), np.diag([1, 1, 0.45, 1]))

    rcount, ccount = X.shape
    print(rcount, ccount)
    ax.plot_surface(
        X,
        Y,
        H,
        cmap=cm.get_cmap(cmap),
        zorder=1,
        rcount=rcount,
        ccount=ccount,
    )

    if ptype == "wireframe":
        ax.plot_wireframe(
            X,
            Y,
            Hnew,
            alpha=max(alpha_surface + 0.2, 1.0),
            color=color_surface,
            zorder=2,
            linewidth=0.5,
            rcount=rcount,
            ccount=ccount,
        )
    elif ptype == "surface":
        ax.plot_surface(
            X,
            Y,
            Hnew,
            alpha=alpha_surface,
            color=color_surface,
            zorder=2,
            rcount=rcount,
            ccount=ccount,
        )

    set_equal(H, ax)

    return ax


if __name__ == "__main__":
    min_acc_climb = 0.25
    min_climb = 4
    # minimum distance
    buffer = 1
    min_altitude = 10
    # amount to penalize height when drawing a* path
    astar_heightcost = 0.001

    xrange, yrange = (0, 60), (0, 60)
    radrange = (5, 18)
    hrange = (1, 50)

    X, Y = generate_xy_grid(xrange, yrange, 1)
    obstacles = generate_obstacles(4, xrange, yrange, radrange, hrange)
    H = place_obstacles(X, Y, obstacles)
    Hnew = get_optimal_grid(H, buffer, min_climb, min_acc_climb, min_altitude)
    # plot
    fig = plt.figure(figsize=(8, 4.5), dpi=120, tight_layout=True)
    ax = plot_grid(fig, X, Y, H, Hnew, ptype="wireframe")

    # get start, end in areas that are all over the map
    start = (2, 2)
    goal = (X.shape[0] - 2, X.shape[1] - 2)
    print("started at {} going to {}".format(start, goal))

    def get_and_plot_path(dist_heur, heur_cost, label, line="r-"):
        xypath = astar(
            X,
            Y,
            Hnew,
            start,
            goal,
            dist_heur=dist_heur,
            heur_cost=heur_cost,
        )
        airpath = np.array([[X[p], Y[p], Hnew[p] + 2] for p in xypath])
        ax.plot(
            airpath[:, 0],
            airpath[:, 1],
            airpath[:, 2],
            line,
            label=label,
            linewidth=3,
            zorder=3,
        )

    dist_heurs = ("euclidean", "least_diff", "lowest")
    heur_costs = (0.0, 0.01, 0.1)
    labels = ("Euclidean", "Least Difference in Height", "Lowest")
    linestyles = ("red", "green", "blue")

    for label, dist_heur, heur_cost, ls in zip(
        labels, dist_heurs, heur_costs, linestyles
    ):
        get_and_plot_path(dist_heur, heur_cost, label, line=ls)
    ax.legend()
    plt.show()
