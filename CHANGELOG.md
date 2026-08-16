# ZXLive changelog


## Unreleased

- Added an interactive tutorial that guides you through the basics of ZXLive, which is shown on first launch and can be accessed again from the **Help > Tutorial** menu (#530).
- Added fault-equivalent rewrites, a set of rewrites that preserve the fault tolerance of a diagram, together with a fault weight threshold for the rewrites that are only fault-equivalent up to a given weight (#427).
- Added a "View > Features" menu for showing or hiding optional features (fault-equivalent rewrites, ZW-calculus vertices and Pauli webs) (#553).
- Optional features are now all disabled by default, and ZXLive asks which ones you want on first launch, right after the tutorial (#563).
- Fixed TikZ proof export so that graphs offset from the origin are normalised, equal signs are vertically centred between adjacent steps, and row wrapping works correctly (#198).
- Fixed a bug which caused the list of available rewrites in proof mode to not be updated until the mouse was hovered over the rewrite panel (#465)
- Fixed closing a tab leaking its panel, so proofs no longer retain their diagram, history and rewrite worker thread after being closed (#562).
- Changed the Ctrl+A shortcut to only select vertices and no longer select edges in order to improve performance (#515)
- Changed graph canvases to start around their diagrams and grow dynamically, so diagrams far from the origin remain visible when entering proof mode (#526).

## v1.0.0
This is the first version where changes were tracked. This version 1.0.0 release brings with it many new features, including:

- First-class support for working with multigraphs: you can now apply complementarity to your heart's content.
- Support for parametrised phases: you can give spiders a phase that contains parameters, such as expressions like `pi/2+a*pi`, where you can specify that `a` has to be a Boolean phase. Several standard rewrites understand when they should apply to parametrised phases.
- Creating custom rewrite rules and using them in your proofs.
- Saving your proofs or exporting them to tikz to be used in your papers.
- Visualising and calculating with Pauli webs on Clifford diagrams.
- Ability to save parts of a diagram as a pattern, to be easily added later to new diagrams.
- Many, many bug fixes and improvements to usability