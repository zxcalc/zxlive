# Using the Pauli Web Panel in ZXLive

The Pauli Web panel in ZXLive provides tools for working with generating Pauli webs, visualizing their structure, and interacting with diagram edges. This page explains how to use the panel and its main functionality. The Pauli webs are computed by PyZX.

## Overview

The Pauli Web panel allows you to:

* Browse available Pauli webs
* See the **type** of each web (e.g. logical, stabilizer, etc.)
* Visualise one or multiple Pauli webs on your diagram
* Inspect which generating Pauli web an edge belongs to
* Configure visualization conventions in the settings


**Where to find the Pauli Web panel**
The Pauli Web panel can be accessed by clicking the Pauli Webs button in the toolbar.

![Pauli Web Panel Location](./_static/pauliwebs_button.png)

---

## Selecting and Adding Pauli Webs

You can insert Pauli webs directly from the list shown on the right in the panel.

### Selecting a single Pauli web

1. Open the Pauli Web panel
2. Click on a Pauli web in the list
3. The selected web will be displayed in your diagram

![Selecting single Pauli web](./_static/selecting_single_web.png)

---

### Selecting multiple Pauli webs

You can select multiple Pauli webs at once. ZXLive will automatically add them correctly and visualise it in the diagram.

1. Hold the multi‑select key (e.g. Ctrl / Cmd)
2. Click multiple Pauli webs in the list
3. Addition of all selected webs will be displayed

![Selecting multiple Pauli webs](./_static/selecting_multiple_webs.png)

---

### Viewing Pauli web types

Each Pauli web in the list displays its type, either

* Logical
* Stabilizer
* Co-stabilizer
* Detecting region

This helps you quickly choose the correct web for your task.

---

## Inspecting Generating Pauli Webs from Diagram Edges

You can inspect which generating Pauli web an edge belongs to directly from the diagram.

### Highlighting a generating Pauli web

1. Double‑click an edge in the diagram
2. ZXLive highlights the generating Pauli web associated with that edge

![Highlight generating Pauli web](./_static/highlighting_edge.png)

---

### Removing highlighting

To remove highlighting:

1. Double‑click anywhere else in the diagram (not on an edge)
2. The highlight will be cleared


---

## Visualization and Coloring Settings

You can customize how Pauli edges are colored via the settings.

### Available options

You can configure:

* **Swap Pauli web colors** – swap the red and green edge meanings depending on your convention
* **Use blue for Y Pauli web** – display Y edges using blue coloring instead of red and green

### Changing the settings

1. Open `Edit > Preferences`
2. Select your preferred coloring convention
3. Apply or save the settings

![Pauli web coloring settings](./_static/settings_pauliwebs.png)

---

## Notes

* Make sure the diagram is a Clifford diagram, as Pauli webs can only be computed for Clifford diagrams in PyZX
* Make sure the diagram is a simple graph (no more then one edge between two vertices) as Pauli webs can only be computed for simple graphs in PyZX.
