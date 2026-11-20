# Auto refresh in `show-deployment.html`

> Replaced by the [live updates](web-ui-live-updates.md) of the redesigned deployment page (2026-11-19): the page is not loaded again, the parts which changed are replaced.

## Current situation

When a stage is running, I need manually refresh the page to see if it's finished or not

## Definition of done
* Automatically refresh content if
  * State of a deployed-object changed
  * State of a stage changed


# Auto refresh in `show_stage_steps`

## Current situation

When a stage is running, I need manually refresh the show_stage_steps to see current state of each processing step

## Definition of done
* Automatically refresh content if
  * State of a stage changed
  * State of a processing step changed
