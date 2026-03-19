bind = "127.0.0.1:8080"
workers = 3
pidfile = 'etc/webapp.pid'

worker_class = "uvicorn.workers.UvicornWorker"