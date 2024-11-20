
## General processing of stages

* Each stage may have defined one or multiple `next_stages` (only the stage name which needs to be unique)
* When a stage has been finished it's next stages will be loaded
* The new id of these stages will be set as list to the finished stage as `next_stage_ids`
* All specific actions to that stage are added
* If all stages has been finished, the deployment is set to status `finished`.


## Parallel workflows

Each step may have one or more `next_stages`.
You can merge them again to one single stept. Just define the same `next_stages` in the parallel steps.

The mergin step can start processing ...
* right after one of the parallel steps has been finished
* after one (or more) of the parallel steps has benn finished
  Just define which stages needs to get finished in the property list `after_stages_finished`