# RotorLab UI Architecture Notes

## 0. What RotorLab Is

**RotorLab** is a software platform for the design, organization, and analysis of rotor and propeller workflows. It is conceived as an engineering and research environment where the user can build parametric geometry, organize technical processes, configure simulations, and inspect results inside a single coherent application.

At its core, RotorLab is not only a geometry tool and not only a simulation launcher. It is intended to be a **workflow-centered engineering platform**. The user does not simply create an isolated model; instead, the user builds a chain of connected technical steps that may include geometry generation, filtering operations, simulation setup, analysis, and result inspection.

This makes RotorLab especially suited to work in contexts where propeller or rotor development is iterative and research-oriented. A user may need to generate a new geometry, pass it through one or more processing stages, evaluate it using simulation methods, compare the results, and then revise the design again. RotorLab is meant to support that full loop inside one structured environment.

A key concept in RotorLab is that the project is organized as a **workflow graph made of modules**. Different module types represent different engineering steps. For example, some modules may define geometry, others may apply filters or transformations, and others may define simulations or result-processing stages. These modules are connected together into a workflow that expresses how the project operates.

Because of this, RotorLab is structured around two complementary ideas:
- a **central orchestration layer**, where the overall workflow is designed and understood
- a set of **specialized environments**, where specific module types are edited in depth

The Orchestrate environment is the main coordination space of the application. It lets the user assemble the workflow by selecting modules, placing them on a canvas, and connecting them. From there, specialized modules open their corresponding detailed environments, such as CAD for geometry work or Simulation for solver setup.

This means RotorLab follows a unified philosophy:
**the workflow graph is the organizing structure of the project, and the specialized environments are opened from that graph.**

RotorLab should therefore be understood as a **multi-environment engineering desktop application** with a persistent shell and a workflow-centered project model. Its interface is designed to let the user move fluidly between high-level process organization and detailed technical work without leaving the main application.

From a product perspective, RotorLab aims to provide:
- a clear way to organize engineering processes as connected workflows
- dedicated environments for different technical activities
- strong support for parametric and modular work
- transparency into the state of the application and project
- a scalable structure that can grow as more module types and environments are added

In practical terms, RotorLab is intended to serve as the workspace in which a user can:
- define and manage rotor or propeller-related workflows
- create and edit module-based engineering pipelines
- open specialized editing environments from those modules
- monitor program state and execution
- maintain a coherent view of the project as one connected system rather than a collection of disconnected tools

The UI architecture described in this document is built to support that vision.

## 1. Top Section Overview

## 1. Top Section Overview

The top section of the RotorLab interface is the primary command and navigation band of the application. It is organized into **three internal rows**, each with a different level of responsibility:

### 1.1 Global Project Controls
This is the uppermost row of the interface. Its purpose is to expose actions that apply to the **entire project or application**, rather than to a specific environment or selected object. These controls should remain stable across all environments so the user always knows where to find the most important project-level actions.

The global project controls row should answer the following user needs:
- Create, open, save, and manage projects
- Access undo/redo and other global editing actions
- Run or validate project-wide operations
- Reach application settings and preferences
- Access help, documentation, and support tools
- See persistent project-level indicators, such as save state or execution state

This row should feel **consistent, compact, and dependable**. Unlike the context toolbar, it should not change dramatically when the user switches between environments such as Orchestrate, CAD, or Simulation.

### 1.2 Environment Switcher
The middle row of the top section is reserved for environment navigation. This row allows the user to move between the major work modes of RotorLab, such as Orchestrate, CAD, Simulation, and Results. It should be visually prominent enough to communicate the current environment, but simpler than the global controls row.

### 1.3 Context Toolbar
The bottom row of the top section is the context-sensitive command area. This row changes according to the current environment and selected object. For example, the CAD environment may show geometry editing actions, while the Simulation environment may show meshing, solver, or boundary-condition actions.

The separation into these three rows creates a clear hierarchy:
- the **top row** manages the application and project as a whole
- the **middle row** changes the user’s work environment
- the **bottom row** provides tools for the current task

This structure supports a professional engineering workflow by keeping stable controls separate from environment navigation and task-specific commands.

## 2. Global Project Controls

The **Global Project Controls** row is the stable command layer of the application. It should contain the most essential actions that users may need at any moment, regardless of which environment they are currently using.

These controls should be grouped into clear categories.

### 2.1 Project Commands
These commands manage the lifecycle of the current project.

Suggested controls:
- New Project
- Open Project
- Open Recent
- Save
- Save As
- Export Project
- Project Settings

These actions should always be available because they affect the entire RotorLab workspace and its persistent data.

### 2.2 Global Edit Commands
These are application-wide editing utilities that are not tied to one environment only.

Suggested controls:
- Undo
- Redo
- Cut
- Copy
- Paste
- Delete
- Duplicate

Some of these may later become context-aware, but their placement in the global controls row gives the user a familiar and stable editing structure.

### 2.3 Project Execution and Validation
Since RotorLab is built around workflows and engineering modules, some project-wide execution controls may belong in the global row.

Suggested controls:
- Validate Project
- Run Workflow
- Stop Execution
- Rebuild Project
- Refresh Dependencies

These controls should remain global only if they act on the full project or the active workflow at a high level. More specialized run actions should remain in the context toolbar.

### 2.4 View and Window Access
The user should have quick access to workspace visibility and layout controls.

Suggested controls:
- Toggle Left Panel
- Toggle Right Panel
- Reset Layout
- Open Console / Logs
- Open Task Monitor

These commands help users manage the interface itself rather than the engineering data.

### 2.5 Application Tools and Preferences
This group contains software-level utilities.

Suggested controls:
- Preferences
- Units and Conventions
- Plugin or Module Manager
- Keyboard Shortcuts
- Theme / Appearance

These should remain available globally because they shape the behavior of the application across all environments.

### 2.6 Help and Documentation
Engineering software benefits from visible help access.

Suggested controls:
- Documentation
- Tutorials
- Example Projects
- Report Issue
- About RotorLab

### 2.7 Persistent Indicators
In addition to buttons and menus, the global controls row may also include compact indicators that communicate the state of the project.

Suggested indicators:
- Current project name
- Save state (saved / unsaved)
- Active workflow name
- Background task indicator
- Warning or error count

These indicators should be subtle but always visible, so the user maintains awareness of the application state.

## 3. Design Principles for the Global Controls Row

The global controls row should follow these design principles:

1. **Stability**: It should not substantially change across environments.
2. **Clarity**: It should contain only project-level controls, not detailed task tools.
3. **Hierarchy**: Frequently used commands such as Save, Undo, and Run Workflow should be easier to access than secondary utilities.
4. **Compactness**: It should remain visually clean and not compete with the environment switcher or context toolbar.
5. **Professional tone**: It should resemble the command structure of serious engineering software rather than a casual creative app.

## 4. Preliminary Role of This Section in the Full UI

Within the complete three-row top section:
- the **Global Project Controls** row provides permanence and trust
- the **Environment Switcher** row provides navigation between work modes
- the **Context Toolbar** row provides task-specific power

This makes the top section both structured and scalable, which is essential for RotorLab as it grows into a multi-environment engineering platform.

## 5. Environment Selection Row

The **Environment Selection** row is the middle row of the top section. Its purpose is to let the user move between the major work contexts that are currently active inside the project. Unlike the global controls row, this row is not focused on application commands. Instead, it is focused on **navigation between active environments**.

This row should be implemented as a **tab-based system**.

### 5.1 Core Navigation Model
The environment row should combine:
- one **fixed anchor tab** for the Orchestrate environment
- a set of **dynamic tabs** created when the user opens or activates another environment

In this model, **Orchestrate** is always present and acts as the home environment of the project. The other tabs are created as needed when the user opens a module in a specialized environment such as CAD, Simulation, Results, or another future workspace.

This creates a navigation system that feels closer to a professional engineering workspace than a simple set of static mode buttons.

### 5.2 Fixed Orchestrate Tab
The **Orchestrate** tab should always be visible and should not be dismissible. It is the persistent top-level view of the project workflow and acts as the central coordination space of RotorLab.

Design guidelines for the Orchestrate tab:
- It should always appear first in the tab row.
- It should have a stable visual identity.
- It should not be closable.
- It should serve as the main return point for the user.
- It should communicate that it is the workflow-level environment rather than a temporary editing tab.

This fixed presence reinforces the idea that the project graph is the central source of truth in RotorLab.

### 5.3 Dynamic Environment Tabs
All other environment tabs should be created dynamically when the user opens a relevant module or workspace.

Examples:
- Opening a geometry module creates a CAD tab.
- Opening a simulation module creates a Simulation tab.
- Opening a result set may create a Results tab.

These tabs represent **active editing or inspection contexts**. They should behave more like workspace tabs than permanent application sections.

Design guidelines for dynamic tabs:
- They should appear to the right of the Orchestrate tab.
- They should be closable when the environment is no longer needed.
- They should preserve context when reopened during the session if possible.
- They should clearly indicate both the environment type and the object being edited.
- They should support multiple open contexts only if this remains manageable and understandable.

A useful labeling scheme would combine the environment type with the edited object, for example:
- `CAD: Propeller_01`
- `Simulation: BEMT_Run_03`
- `Results: Acoustic Sweep A`

This reduces ambiguity and helps the user understand what each tab refers to.

### 5.4 Meaning of Tabs in RotorLab
These tabs should not be interpreted as generic browser-style tabs. Instead, they should represent **live work contexts tied to nodes or views in the project graph**.

A tab should answer the question:
**What am I editing or viewing right now, and in which environment?**

This means each environment tab should preserve the relationship between:
- the active project
- the selected workflow object or module
- the environment used to edit or inspect it

This design keeps navigation coherent and reduces the feeling of jumping between disconnected tools.

### 5.5 Recommended Tab Behavior
The row should follow a predictable tab behavior model.

Suggested behaviors:
- Clicking **Orchestrate** returns the user to the workflow canvas.
- Double-clicking or otherwise opening a module from Orchestrate creates or activates the corresponding environment tab.
- Selecting a tab restores that environment’s workspace state.
- Closing a tab closes only the current work context, not the underlying project object.
- If the user reopens the same object, the software may restore the previous tab state instead of creating duplicates.

This keeps tabs lightweight while still allowing fluid movement between project orchestration and specialized editing.

### 5.6 Duplicate Prevention and Tab Reuse
The interface should avoid unnecessary duplication of tabs.

Recommended rule:
- if the user opens an object that already has an active tab in the same environment, RotorLab should activate the existing tab instead of creating a new one

For example:
- opening the same geometry node twice should focus the existing `CAD: Propeller_01` tab
- opening the same simulation case again should focus the existing simulation tab for that case

This helps prevent clutter and keeps the tab row understandable.

### 5.7 Tab Identity and Naming
Tab titles should be short but descriptive. They should communicate two things:
1. the **environment type**
2. the **current object or workspace name**

Suggested naming pattern:
`[Environment]: [Object Name]`

Examples:
- `CAD: Rotor_A`
- `Simulation: Hover_Case_1`
- `Results: Noise Study`

If space is limited, the interface may shorten long object names, but the full name should remain visible on hover.

### 5.8 Visual Hierarchy
The environment selection row should be visually clearer than a simple toolbar, but lighter than the global controls row.

Design guidelines:
- The active tab should be strongly distinguishable.
- The Orchestrate tab should feel foundational, not temporary.
- Dynamic tabs should look related but slightly more transient.
- Tab styling should not be overly decorative; clarity is more important than visual complexity.
- If icons are used, they should indicate environment type rather than act as decoration.

Example icon logic:
- Orchestrate → graph/workflow icon
- CAD → geometry or cube icon
- Simulation → solver or waveform icon
- Results → chart icon

### 5.9 Overflow and Scalability
As the project grows, the user may open multiple contexts. The environment row should therefore handle overflow gracefully.

Suggested strategies:
- horizontal tab scrolling
- a dropdown for hidden tabs
- pinning only the Orchestrate tab while allowing the rest to scroll
- optional tab grouping in future versions if needed

The row should remain usable even when many contexts are open.

### 5.10 Relationship to the Context Toolbar
The environment row should directly control the contents of the context toolbar below it.

In practical terms:
- selecting **Orchestrate** loads the orchestration tools into the context toolbar
- selecting a **CAD** tab loads geometry tools
- selecting a **Simulation** tab loads simulation tools
- selecting a **Results** tab loads result-inspection tools

This creates a clear relationship between the middle and bottom rows of the top section.

### 5.11 Design Principles for the Environment Row
The environment selection row should follow these principles:

1. **Anchor first**: Orchestrate is always present and acts as the project home.
2. **Context-based navigation**: dynamic tabs represent real work contexts, not generic pages.
3. **Clarity of identity**: every tab should clearly communicate what it contains.
4. **Low clutter**: duplicate tabs should be prevented whenever possible.
5. **Fast switching**: users should be able to move quickly between workflow design and specialized editing.
6. **Scalability**: the row should remain usable when several contexts are open.

### 5.12 Role of the Environment Row in RotorLab
This row is not only a navigation strip. It is a structural part of RotorLab’s workflow philosophy.

It reinforces the idea that:
- the project is centered in Orchestrate
- specialized environments are opened from project objects
- the user can move fluidly between coordination and detailed editing without leaving the main application shell

For RotorLab, this makes the environment row one of the most important pieces of UI coherence in the entire application.


## 6. Context Toolbar Row

The **Context Toolbar** is the bottom row of the three-row top section. Its purpose is to expose the commands and tools that are relevant to the **currently active environment**.

Unlike the Global Project Controls row, which remains stable across the application, the Context Toolbar is explicitly **dynamic**. Its content changes when the user changes environments.

This means that RotorLab does not have one universal context toolbar. Instead, each environment will define its own toolbar structure, commands, and interaction logic.

For now, the role of this row is defined at a high level:
- it belongs to the active environment
- it changes dynamically when the active environment changes
- it provides task-specific tools rather than project-level controls
- its detailed design will be defined later, together with each environment

This creates a clean hierarchy across the three rows of the top section:
- the **top row** contains stable global project controls
- the **middle row** selects the active environment
- the **bottom row** provides the tools of that environment

The Context Toolbar therefore acts as the adaptive layer of the top section. It allows RotorLab to keep one persistent application shell while changing the active toolset according to the user’s current workspace.

Its detailed behavior, layout, and commands should be specified separately when defining each individual environment.


## 7. Middle Section Overview

The **middle section** is the main workspace area of RotorLab. It is the part of the interface where the user performs most engineering and workflow design tasks.

Unlike the top section, which is organized as fixed horizontal rows, the middle section should be based on a **windowed workspace model**. Inside this area, the user works with windows that can be arranged according to the needs of the current environment.

### 7.1 Windowed Workspace Model
The middle section should support workspace windows that can be:
- moved within the workspace
- docked into arranged layouts
- floated when needed
- minimized when temporarily not in use
- closed when no longer needed

This gives RotorLab a more professional engineering-software feel and allows users to organize their workspace according to the task at hand.

The purpose of this model is not to make the interface feel like a generic desktop, but to provide controlled flexibility inside the main application shell.

### 7.2 Workspace Arrangement
Windows inside the middle section should be able to coexist in structured layouts. Depending on the environment, the user may prefer:
- a side-by-side layout
- a stacked or tabbed arrangement
- a dominant main window with one or more support windows
- floating utility windows for temporary tasks

The exact arrangement will depend on the environment, but the workspace model should remain consistent across RotorLab.

### 7.3 Role of the Middle Section
The middle section is where each environment expresses its own working style.

For example:
- **Orchestrate** uses the middle section for graph construction and module selection
- **CAD** may use it for a 3D viewport and supporting editors
- **Simulation** may use it for setup, previews, and solver-related views
- **Results** may use it for plots, tables, and comparative analysis views

This makes the middle section the primary adaptive workspace region of the application.

## 8. Orchestrate Environment

The **Orchestrate** environment is the central workflow-design space of RotorLab. It is the main environment in which the user constructs, edits, and manages the project workflow.

Its primary purpose is to let the user assemble engineering processes by selecting modules, placing them into a canvas, and connecting them into a coherent workflow.

### 8.1 Core Role of Orchestrate
The Orchestrate environment should function as the **workflow composition layer** of the application.

It should allow the user to:
- browse available modules
- place modules into the workflow canvas
- connect modules together
- define the structure of the engineering process
- understand the relationships between geometry, filtering, simulation, and other processing steps

This environment acts as the project’s central coordination space and should remain closely tied to the fixed **Orchestrate** tab in the top section.

### 8.2 Main Windows of the Orchestrate Environment
For the first definition of this environment, the Orchestrate workspace contains **two main windows**:
- a **Module Selection** window
- a **Canvas** window

These two windows define the essential interaction loop of the environment:
1. the user selects a module from the module list
2. the user drags it into the canvas
3. the user connects modules inside the canvas to design the workflow

### 8.3 Module Selection Window
The **Module Selection** window is the source panel for the workflow components available in RotorLab.

Its purpose is to present the list of available module types that the user can add to the workflow.

At a high level, this window should contain categories such as:
- geometric modules
- simulation modules
- filter modules
- analysis modules
- export or utility modules
- other future categories as RotorLab grows

The main interaction model is:
- the user browses the available modules in this window
- the user drags a chosen module from this list into the canvas

This interaction should feel similar in spirit to engineering workflow tools such as **ANSYS Workbench**, where available system elements are selected from a library and placed into a project workspace.

### 8.4 Design Role of the Module Selection Window
The Module Selection window should be treated as a **library window**, not as a secondary canvas.

Its role is to:
- organize the available building blocks of the workflow
- help the user understand the types of operations available
- serve as the entry point for constructing a new workflow step

Because of this, its design should emphasize:
- clear categorization
- easy scanning
- drag-and-drop usability
- enough structure to scale when more module types are added

Its detailed visual design can be specified later, but its functional identity should already be established as the source of workflow modules.

### 8.5 Canvas Window
The **Canvas** window is the primary working area of the Orchestrate environment.

This is where the user places modules and designs the workflow itself.

The Canvas window should allow the user to:
- receive dragged modules from the Module Selection window
- position modules spatially in the workspace
- connect modules together
- organize the visual structure of the workflow
- understand the order and dependency relationships of the process

The canvas is therefore the main representation of the engineering workflow.

### 8.6 Workflow Construction Model
The workflow should be built by placing modules on the canvas and connecting them.

At a high level, the user interaction is:
1. choose a module type from the Module Selection window
2. drag it into the Canvas window
3. place it in the desired position
4. create connections between modules
5. continue building the workflow as a graph of linked processing steps

This makes the Orchestrate environment a **visual workflow graph editor**.

### 8.7 Relationship Between Modules and Other Environments
Within the Orchestrate canvas, the placed modules represent the project elements that may later open other specialized environments.

Examples:
- a **geometric module** may open a CAD environment tab
- a **simulation module** may open a Simulation environment tab
- a **results-related module** may later open a Results environment tab

This means the Orchestrate environment is not isolated. It is the central graph from which the rest of RotorLab’s specialized workspaces are accessed.

### 8.8 Workspace Structure in Orchestrate
In its initial form, the Orchestrate environment should be centered on a simple and clear arrangement:
- the **Module Selection** window provides the module library
- the **Canvas** window provides the workflow graph area

This arrangement should support docked layouts, but also remain compatible with the broader middle-section window model so that windows may later be floated, resized, minimized, or rearranged as needed.

### 8.9 Design Principles for the Orchestrate Environment
The Orchestrate environment should follow these principles:

1. **Workflow-first**: its main purpose is to build and understand the project workflow.
2. **Visual clarity**: the user should easily understand what modules exist and how they connect.
3. **Drag-and-drop construction**: adding modules should feel direct and natural.
4. **Scalability**: the canvas and module library should support more module types over time.
5. **Centrality**: this environment should feel like the main coordination space of the project.
6. **Continuity**: modules placed in the workflow should connect naturally to the specialized environments they open.

### 8.10 Role of Orchestrate in RotorLab
The Orchestrate environment is the structural core of RotorLab’s user workflow.

It is where the user defines the high-level engineering process before entering specialized environments for detailed work.

Because of this, it should serve as:
- the project’s main composition space
- the central graph of relationships between modules
- the main starting point for opening CAD, Simulation, and future environments

This reinforces one of the key ideas of RotorLab’s UI architecture:
**the workflow graph is the organizing structure of the project, and the specialized environments are opened from that graph.**

## 9. Bottom Section Overview

The **bottom section** of the RotorLab interface is the **status bar**. Its purpose is to provide continuous, lightweight feedback about the current state of the application without interrupting the user’s work.

Unlike the middle section, which is a workspace, and unlike the top section, which is focused on commands and navigation, the bottom section is primarily informational. It should communicate what the program is doing at a given moment and give the user quick access to more detailed runtime information.

### 9.1 Core Role of the Status Bar
The status bar should act as the application’s **state feedback layer**.

It should help the user understand, at a glance:
- whether the program is idle or busy
- what operation is currently taking place
- whether attention is needed
- where to look for more detailed execution information

The status bar should remain visible across environments and should adapt to the current state of the software.

### 9.2 State Message
The main element of the status bar is a **state message** that changes dynamically according to what is happening in the program.

Examples of possible state messages include:
- `Ready`
- `Running simulation`
- `Regenerating geometry`
- `Validating workflow`
- `Loading project`
- `Execution stopped`
- `Error during simulation`

This message should be short, clear, and easy to scan. Its purpose is not to provide detailed logs, but to give the user immediate awareness of the current program state.

### 9.3 Adaptive Behavior
The state message should adapt to the active state of the application.

This means it may reflect:
- general application state when nothing specific is selected
- project-level operations such as loading, saving, or validating
- environment-related actions such as running a simulation or regenerating a geometry
- warning or error conditions when they occur

The message should always prioritize the most relevant active state so the user is not left guessing about what the software is doing.

### 9.4 Console Logs Access
In addition to the state message, the status bar should include a **button that opens the console logs**.

This button provides a direct path from lightweight status feedback to more detailed execution information.

Its purpose is to let the user inspect:
- runtime messages
- execution progress details
- warnings
- errors
- diagnostic information

This is especially important in an engineering application, where users often need more transparency into what the software is doing.

### 9.5 Relationship Between Status Bar and Console
The bottom section should be designed so that the status message and the console access complement each other:
- the **status message** gives immediate, high-level awareness
- the **console logs** provide deeper operational detail when needed

This creates a two-level feedback model:
1. a compact state indicator always visible in the shell
2. a deeper diagnostic view available on demand

### 9.6 Design Principles for the Bottom Section
The bottom section should follow these principles:

1. **Always visible**: the user should always have access to current state feedback.
2. **Lightweight**: the bar should remain compact and not distract from the main workspace.
3. **Adaptive**: the message should change according to what the program is doing.
4. **Clear**: messages should be short and understandable.
5. **Transparent**: the console logs button should make it easy to inspect deeper execution details.

### 9.7 Role of the Bottom Section in the Full UI
Within the complete RotorLab interface:
- the **top section** provides commands, navigation, and environment tools
- the **middle section** provides the workspace and windowed environments
- the **bottom section** provides live state feedback and access to runtime logs

This makes the bottom section the final layer of the shell: a compact but important source of operational awareness.
