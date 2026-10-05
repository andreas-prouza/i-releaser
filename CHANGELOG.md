# 3.1.0

* Store source file name in deploy-objects
* Add support to run sql scripts as deployment
* Add properties for deploy-objects
* Styles
* Bugfixes
* Store logs in meta_file dir to shrink db size
* Option to automatically run next stage
* Define editable fields in custom-data
* Auto refresh of the deployment page and the stage steps window
* Finish permission maintenance
* Faster processing steps: no more piling up log handlers, less logging and fewer DB queries per step, DB indexes
* Log the duration (prepare, execute, save) of each processing step
* Database uses WAL mode: back up `var/app.sqlite-wal` and `var/app.sqlite-shm` together with `var/app.sqlite`
* Deployment history logs are stored again