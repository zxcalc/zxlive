# Fault Equivalent Rewrites in ZXLive

A fault equivalent rewrite is a transformation that ensures the fault weight in the pre-rewrite graph is either maintained or reduced in the post-rewrite graph. That is, these rewrites do not introduce any new faults, nor allow any existing faults to propagate uncontrollably. The fault weight refers to the measure of errors (faults) in a quantum circuit, usually the number of potential error occurences within the circuit. Most implemented rewrites are fully fault equivalent, however some only preserve fault equivalence up to a certain fault weight. ZXLive gives a graphical way to work with these rewrites

## Using Fault Equivalent Mode

ZXLive makes it easy to work with fault equivalent rewrites using **Fault Equivalent Mode**. 

How to use Fault Equivalent Mode:
1. Activate Fault Equivalent Mode: in the proof panel, click the FE toggle in the toolbar to enable (and disable) FE mode (highlighted in red or 1 in image below)
2. View FE rules: this mode will only show the rewrite rules that preserve fault equivalence
3. Fault Weight Input: Set a maximum fault weight threshold in the input box next to the toggle. ZXLive will then only show the rewrites that abide by this fault threshold. (highlighted in green or 2 in image below)

<img src="./_static/FE_rewrites_toolbar.png" alt="Fault Equivalent Rewrites Toolbar" width="350"/>

:::{note}
Custom fault equivalent rules are not currently supported.
:::

:::{note}
Not all fault-equivalent rewrites are implemented. In case the implemented FE rules are insufficient, it may be necessary to temporarily switch to basic rewrites, and then return to Fault Equivalent Mode later.
:::

## w-Fault Tolerant Rewrite Example
Below you can find an example of how specifying a fault weight can change the outcome of applying the FE Unfuse-2n rewrite.


| Before Rewrite | Rewrite (weight = ∞) | Rewrite (weight = 2) |
|---------------|---------------------|----------------------|
| <img src="./_static/FE_example_pre_rule.png" width="250"/> | <img src="./_static/FE_example_w_inf.png" width="250"/> | <img src="./_static/FE_example_w_2.png" width="250"/> |

The difference occurs because some instances of the FE Unfuse‑2n rewrite can introduce additional internal nodes that help propagate faults to the boundary. When the fault weight is set to infinity, all such rewrites are allowed, resulting in a diagram with more nodes. When a finite fault weight is specified (e.g. w=2), rewrites that would create faults exceeding that weight are blocked, so fewer internal nodes are added and the resulting diagram is smaller. Thus, fault equivalence up to the specified weight is preserved.

A formal definition of w-fault-equivalent rewrites and the boundary push-out property can be found in [Rodatz et al., 2025](https://doi.org/10.48550/arXiv.2506.17181).


## References
Rodatz, B., Poór, B., & Kissinger, A. (2025). *Fault Tolerance by Construction*. [arXiv:2506.17181v3 [quant-ph]](https://doi.org/10.48550/arXiv.2506.17181).
