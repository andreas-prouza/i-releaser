# Processing service

For very large deployments, it's maybe better to precess it by an independend service. 

This service can process the deployment asyncron. 
Even if the http job ends, the service still continues processing.

## Solution

* The web app adds the run of a stage as job to a queue (table `processing_jobs`) and wakes up the service over a local socket, so the stage starts immediately.
* The service (`serviceapp/service.py`, logic in `modules/processing_service.py`) takes the job from the queue and runs it in its own process (fork).
* Web app and service only communicate over the database. The web app shows the progress like before.
* Global switch `C_PROCESSING_MODE` in `etc/constants.py`: `thread` (default, like before) or `service`.
* Jobs whose process died are set to `failed` together with their stage.
* Documentation: [processing-service.md](../../processing-service.md)

## Definition of done
* A stage which is run by the service keeps running when the web app or the service ends
* The stage starts without a noticeable delay
* If the service is not running, the stage is queued and the user gets a warning. It's run when the service has been started
* A queued stage is shown in the web app and can be removed from the queue
* The run is logged with the user who started it
* A stage whose process died is set to `failed` and can be run again
* Without `C_PROCESSING_MODE = 'service'` nothing changes
