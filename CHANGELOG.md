# ZXLive changelog


## Unreleased

- Added an interactive onboarding tutorial. A guided overlay walks new users through the canvas, tools and sidebars on first launch, and a dedicated tour introduces proof mode the first time a derivation is started. The welcome screen offers a **Quick start** (short, functional) as well as the **full tour**, so returning users can skip the explanations. The spotlighted element gently pulses and the explanation card points at it. Both tours can be replayed any time from **Help → Interactive Tutorial** (Editor Tour / Proof Mode Tour), and auto-start can be toggled under **Preferences → Show tutorial on startup**.


## v1.0.0
This is the first version where changes were tracked. This version 1.0.0 release brings with it many new features, including:

- First-class support for working with multigraphs: you can now apply complementarity to your heart's content.
- Support for parametrised phases: you can give spiders a phase that contains parameters, such as expressions like `pi/2+a*pi`, where you can specify that `a` has to be a Boolean phase. Several standard rewrites understand when they should apply to parametrised phases.
- Creating custom rewrite rules and using them in your proofs. 
- Saving your proofs or exporting them to tikz to be used in your papers.
- Visualising and calculating with Pauli webs on Clifford diagrams.
- Ability to save parts of a diagram as a pattern, to be easily added later to new diagrams.
- Many, many bug fixes and improvements to usability