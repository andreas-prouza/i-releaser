# Processing service

By default a stage is run by the web app: in a thread of the web server job.
If that job ends (restart of the web server, a crashed worker, ...), the stage ends with it and stays in status `in process`.

The processing service is an independent job which runs the stages instead.
The web app only tells it what to run.

* A stage keeps running when the web app ends.
* A stage keeps running when the service is stopped or restarted.
* Each stage runs in its own process. It can't influence the web app or another stage.
* A stage whose process died is set to `failed` automatically, so it can be run again.


## How it works

```
web app                                processing service

Run stage
  1. checks the stage (permission, status)
  2. adds a job to the queue
  3. wakes up the service  ---------->  4. takes the job from the queue
                                        5. starts an own process for it
                                           which runs the stage
shows the progress as usual  <--------  status of stage, steps and logs
```

* The queue is the table `processing_jobs` in the database (`var/app.sqlite`). Web app and service only communicate over the database.
* The wake up (a local socket in `var/`) makes sure the stage starts immediately. If it gets lost, the service finds the job with its next look into the queue (`C_SERVICE_POLL_INTERVAL`).
* The process of a job is a copy of the running service. Python, the modules and the scripts are already loaded, so there is no waiting time.
* A stage is run in the name of the user who started it.
* Following stages which are run automatically (`run_immediate`) are processed by the same job.


## Set up

1. Switch the mode in `etc/constants.py`

   ```python
   C_PROCESSING_MODE = 'service'
   ```

2. Restart the web app

3. Start the service

   ```bash
   [andreas@idev i-releaser]$ cd serviceapp
   [andreas@idev serviceapp]$ ./service start
   Start service
   Service is running ...
   ```

   Also available: `./service stop`, `./service status`, `./service restart`

Run the service with the same user as the web app. Both use the same database, logs and meta directories.

The current state is shown in the web app: `Settings` &rarr; `General` &rarr; `Processing of stages`.
There you also find the last jobs with their status and error.


## Settings

All settings are in `etc/constants.py`.

| Setting | Default | Description |
|---|---|---|
| `C_PROCESSING_MODE` | `'thread'` | `'thread'`: stages are run by the web app. `'service'`: stages are run by the processing service. |
| `C_SERVICE_MAX_PARALLEL_JOBS` | `4` | Number of stages which are run at the same time. Further stages wait in the queue. |
| `C_SERVICE_POLL_INTERVAL` | `5` | Seconds between two looks into the queue, if the service was not woken up. Also the time until a died job process is noticed. |
| `C_SERVICE_HEARTBEAT_INTERVAL` | `10` | Seconds between two signs of life of a running job. |
| `C_SERVICE_HEARTBEAT_TIMEOUT` | `60` | Seconds without a sign of life until a job is seen as dead. |
| `C_SERVICE_SOCKET` | `var/processing-service.sock` | Socket for the wake up. |
| `C_SERVICE_PID_FILE` | `var/processing-service.pid` | Process id of the service. If you change it, also change it in `serviceapp/service`. |


## What happens if ...

| Situation | Behaviour |
|---|---|
| The web app is stopped | Running stages continue. |
| The service is stopped | Running stages continue. They are not affected by the restart of the service. |
| A stage is started while the service is not running | The stage is added to the queue and you get a warning. The stage shows the button `queued`. It's run as soon as the service has been started. |
| You don't want to wait for the service | Click on `queued` to remove the stage from the queue. |
| A job process dies (killed, restart of the system) | The job, its stage and the deployment are set to `failed`. The hook `stage_failed` is called. The stage can be run again (`Continue processing` starts with the step which was not finished). |
| A stage is started twice | The second start is rejected as long as the first one is queued or running. |
| A deployment is canceled | Its stages are removed from the queue. A stage which is already running is not stopped (same behaviour as without the service). |
| More stages are started than `C_SERVICE_MAX_PARALLEL_JOBS` | They wait in the queue (button `queued`) and start one after another. |


## Good to know

* Steps and scripts run in the same environment as with the web app: the working directory is `webapp/` and the configs of `webapp/etc` are available.
* Scripts are loaded when the service starts. Restart the service after you changed a file in `scripts/` (like you have to restart the web app in mode `thread`).
* [Hooks](workflow.md#hooks) which are triggered by the run of a stage (`stage_started`, `stage_finished`, `stage_failed`, `deployment_finished`) run in the process of the job. The other hooks still run in the web app.
* Logs of the service: `log/service.log` (and `log/service_nohup.log` for errors during the start). The logs of a stage are stored with the deployment as usual.
* Switching back to `'thread'`: stages which are still in the queue are only run by the service. Let the service finish them or remove them from the queue first.
