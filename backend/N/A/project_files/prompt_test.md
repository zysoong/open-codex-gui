
This is a very smart function to clamp spline b to a: 
---
import numpy as np
from pydantic import BaseModel
from scipy.interpolate import BSpline, splrep
from typing import Literal
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D


class Point3D(BaseModel):
    X: float
    Y: float
    Z: float

    class Config:
        frozen = True

    def to_array(self):
        return np.array([self.X, self.Y, self.Z])

    @staticmethod
    def from_array(arr: np.ndarray):
        return Point3D(X=float(arr[0]), Y=float(arr[1]), Z=float(arr[2]))


class REBSpline(BaseModel):
    control_points: list[Point3D]
    knots: list[float]
    degree: int = 0

    def model_post_init(self, __context=None):
        self.degree = len(self.knots) - len(self.control_points) - 1

    def to_scipy_bspline(self):
        control_array = np.array([[p.X, p.Y, p.Z] for p in self.control_points])
        knot_array = np.array(self.knots)
        return BSpline(t=knot_array, c=control_array, k=self.degree)

    @property
    def domain(self):
        p = self.degree
        return self.knots[p], self.knots[-p - 1]


def compute_arc_length(spline: REBSpline, n_samples: int = 1000) -> float:
    """Compute the geometric arc length of a spline."""
    scipy_spline = spline.to_scipy_bspline()
    u_start, u_end = spline.domain

    eps = 1e-10
    u = np.linspace(u_start + eps, u_end - eps, n_samples)
    points = scipy_spline(u)

    segments = np.diff(points, axis=0)
    lengths = np.linalg.norm(segments, axis=1)

    return np.sum(lengths)


def connect_reb_splines(
        a: REBSpline,
        b: REBSpline,
        tol: float = 1e-9,
        n_samples: int = 500,
        smoothing_factor: float = 0.0,
        remove_duplicates: bool = True,
        duplicate_tol: float = 1e-6
) -> REBSpline:
    """Connect two B-splines into a single smooth B-spline (ORIGINAL ROBUST VERSION)."""
    spline_a = a.to_scipy_bspline()
    spline_b = b.to_scipy_bspline()

    u_start_a, u_end_a = a.domain
    u_start_b, u_end_b = b.domain

    eps = 1e-10
    u_a = np.linspace(u_start_a, u_end_a - eps, n_samples)
    u_b = np.linspace(u_start_b, u_end_b - eps, n_samples)

    points_a = spline_a(u_a)
    points_b = spline_b(u_b)

    end_a = spline_a(u_end_a - eps)
    start_b = spline_b(u_start_b + eps)

    dist = np.linalg.norm(end_a - start_b)

    if dist > tol:
        raise ValueError(f"Splines do not connect: distance = {dist:.6f} > tol = {tol}")

    shared_point = (end_a + start_b) / 2.0

    combined_points = np.vstack([
        points_a[:-1],
        shared_point.reshape(1, 3),
        points_b[1:]
    ])

    if remove_duplicates:
        unique_points = [combined_points[0]]
        for i in range(1, len(combined_points)):
            dist_to_last = np.linalg.norm(combined_points[i] - unique_points[-1])
            if dist_to_last > duplicate_tol:
                unique_points.append(combined_points[i])
        combined_points = np.array(unique_points)

    t_combined = np.linspace(0, 1, len(combined_points))

    degree = 3
    tck_x = splrep(t_combined, combined_points[:, 0], k=degree, s=smoothing_factor)
    tck_y = splrep(t_combined, combined_points[:, 1], k=degree, s=smoothing_factor)
    tck_z = splrep(t_combined, combined_points[:, 2], k=degree, s=smoothing_factor)

    new_knots = tck_x[0]
    n_coeffs = len(new_knots) - degree - 1

    coeffs_x = tck_x[1][:n_coeffs]
    coeffs_y = tck_y[1][:n_coeffs]
    coeffs_z = tck_z[1][:n_coeffs]

    min_len = min(len(coeffs_x), len(coeffs_y), len(coeffs_z))
    coeffs_x = coeffs_x[:min_len]
    coeffs_y = coeffs_y[:min_len]
    coeffs_z = coeffs_z[:min_len]

    if min_len != n_coeffs:
        n_coeffs = min_len
        n_knots_needed = n_coeffs + degree + 1
        if len(new_knots) != n_knots_needed:
            new_knots = np.concatenate([
                [0.0] * (degree + 1),
                np.linspace(0, 1, n_coeffs - degree + 1)[1:-1],
                [1.0] * (degree + 1)
            ])

    new_control_points = np.column_stack([coeffs_x, coeffs_y, coeffs_z])
    control_point_list = [
        Point3D(X=float(pt[0]), Y=float(pt[1]), Z=float(pt[2]))
        for pt in new_control_points
    ]

    result = REBSpline(
        control_points=control_point_list,
        knots=new_knots.tolist()
    )

    return result
---

It basically firstly find the anchor point by averaging a's tail and b's head, 
then sparse sampling around the anchor region and dense sample the part far away. 
This makes connection point C1 coninuity. 

Now I want an extended solution: 
Now I want 1-1-1 connection instead of 1-1 like this. 
you have one main_spline, one predecessor_spline and one successor_spline. 
And in this case we do not need parameter connections: list[tuple[int, int]] anymore. 

So  your function should contain following parameters: 
main_spline: REBSpline,
predecessor_spline: REBSpline,
successor_splines: REBSpline,
...  (other parameters you think are important)

You would re-implement the function clamp_multiple_splines, making the head of main spline being clamped to tail of predecessor spline, 
and tail of main spline being clamped to head of successor splineåå
Deepdive into the code connect_reb_splines and connect_reb_splines_separated to get ideas here. 
We would like to make sure that every clamp will maintain C1 connectivity (similar to connect_reb_splines), 
which means if we have main_spline a, and predecessor spline b; and successor c you need to make sure that the connection point of b-a, a-c are all C1 continuous. 

One solution is to just make the predecessor and successor splines absolutely unchanged
The function should return clamped main spline. 
After writing the function, you would also want to create some examples to test numerically, and to visualize
Also calculate the positional consistency on every point of the main before and after clamping, and the c1 continuity error on connection point. 
Also I need to guarantee the start point (head) consistency of predecessors and end point consistency of successors. And I also want the shapes of main spline won't change too much if possible
