# Proof mode interactions

In proof mode there are two quick ways to apply rewrites without touching the rule panel on the left: the **magic wand** and **drag and drop**. Both record a step in the proof history exactly like clicking a named rule.

## The magic wand

Press `w` (or click the wand icon in the toolbar) to activate the magic wand. Hold and drag to draw a trace over the diagram. What happens depends on what the trace crosses.

**Adding an identity spider.** Draw the wand once over a plain wire. ZXLive inserts a phaseless spider of whichever type is selected by the **Z** / **X** buttons next to the wand icon.

```{figure} _static/magic_wand_add_identity.gif
:alt: Adding an identity spider with the magic wand
:align: center

Draw the wand over a wire to insert an identity spider.
```

**Removing an identity spider.** Draw the wand through any degree-2 phaseless spider. The spider is removed and replaced by a plain wire. This is equivalent to clicking **Basic rules > Remove identity** in the rule panel.

```{figure} _static/magic_wand_remove_identity.gif
:alt: Removing an identity spider with the magic wand
:align: center

Draw the wand through a two-legged phaseless spider to remove it.
```

**Applying the Hopf rule.** When a Z and X spider share parallel edges, draw the wand once across those edges. ZXLive removes the largest even number of parallel edges it can in one stroke. ZXLive also applies this rule automatically whenever a fusion creates parallel edges — you may have seen it happen silently in the [getting started tutorial](gettingstarted.md).

```{figure} _static/magic_wand_hopf.gif
:alt: Removing parallel edges with the magic wand
:align: center

Stroke the wand over parallel edges between complementary spiders to remove them.
```

**Unfusing (slicing) a spider.** Draw the wand *through* a spider from one side to the other. The edges on one side of the trace are moved to a newly created copy of the spider, splitting it in two connected spiders. Without Shift, the original phase stays on one spider and the new one gets phase 0. Hold **Shift** while drawing to open a dialog and choose any phase split explicitly. This works on Z, X, Z-box, and W spiders.

```{figure} _static/magic_wand_unfuse.gif
:alt: Unfusing a spider with the magic wand
:align: center

Slice a spider by drawing the wand through it. Hold Shift to set the phase of the new spider.
```

## Drag and drop

In select mode (`s`), drag a spider and release it on top of a neighbouring spider. ZXLive checks which rewrite applies and performs it automatically, recording the step in the proof history.

The precedence of rewrites is: fuse > copy 0/π > push Pauli > strong complementarity (bialgebra). If none applies, the spider is simply moved.

**Fusing spiders.** Drag a Z spider onto an adjacent Z spider (or X onto X) to fuse them into one spider whose phase is the sum of the two phases.

```{figure} _static/drag_fuse.gif
:alt: Fusing spiders by drag and drop
:align: center

Drag one spider onto a same-colour neighbour to fuse them.
```

**Strong complementarity.** Drag a Z spider onto an adjacent X spider (or vice versa). ZXLive applies the bialgebra rule, expanding the single edge into a complete bipartite subgraph.

```{figure} _static/drag_bialgebra.gif
:alt: Applying bialgebra by drag and drop
:align: center

Drag complementary spiders together to apply the strong complementarity rule.
```

**Copying a 0/π spider.** Drag a spider whose phase is 0 or π and has exactly one non-boundary neighbour onto that neighbour. The π phase is copied onto every other leg of the neighbour and the neighbour's phase is negated. (Boundary wires connecting to the circuit edge do not count as spider legs.)

```{figure} _static/drag_copy_pi.gif
:alt: Copying a pi spider by drag and drop
:align: center

Drag a 0 or π spider onto its neighbour to distribute the phase.
```

**Pushing a Pauli.** Drag an arity-2 spider with phase π onto one of its neighbours. The π phase commutes through, negating the neighbour's phase and leaving a π spider on the other side.

```{figure} _static/drag_push_pauli.gif
:alt: Pushing a Pauli spider by drag and drop
:align: center

Drag an arity-2 π spider onto its neighbour to push the Pauli through.
```

## Regenerating these images

The animations on this page are generated programmatically. After UI changes, regenerate them with:

```bash
QT_QPA_PLATFORM=offscreen python3 doc/scripts/generate_proof_mode_assets.py
```

Requires `ffmpeg` on your PATH.
