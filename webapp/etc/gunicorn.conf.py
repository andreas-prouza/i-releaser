bind = "0.0.0.0:2001"
workers = 3
threads = 4  # Set the number of threads per worker
pidfile = 'etc/webapp.pid'
worker_class = "uvicorn.workers.UvicornWorker"
loglevel = 'debug'