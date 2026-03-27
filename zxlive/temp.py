#%%
from typing import Any

import numpy as np

# %%
def pivot(adj_mat: np.matrix, i: int, j: int) -> Any:
    row_i = adj_mat[i, :]
    row_j = adj_mat[j, :]
    return (adj_mat + row_i.T @ row_j + row_j.T @ row_i) % 2


# %%
A = np.matrix([
    [1,1,1,0,0,1],
    [1,1,1,1,0,0],
    [1,1,1,0,1,1],
    [0,1,0,1,1,1],
    [0,0,1,1,1,0],
    [1,0,1,1,0,1]
])
# %%
print(pivot(A, 0, 1))
# %%
print(pivot(A, 0, 2))
