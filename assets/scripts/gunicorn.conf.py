# gunicorn.conf.py
#
# This is a sample Gunicorn configuration file for a Django project.
#
# To use this configuration, run Gunicorn with the --config flag:
# gunicorn --config gunicorn.conf.py core.wsgi:application

import multiprocessing

# The socket to bind to.
# A TCP socket: '127.0.0.1:8000'
# Or a Unix socket: 'unix:/run/gunicorn.sock'
# A Unix socket is recommended for performance when Gunicorn and the reverse proxy (e.g., Nginx)
# are on the same machine.
# When running in Docker, you should bind to '0.0.0.0' to accept connections
# from the Docker network.
bind = "[::]:8000"

# The number of worker processes for handling requests.
# A common recommendation is (2 * number_of_cpu_cores) + 1.
# This setting is crucial for performance and should be tuned based on your server's resources.
# workers = 1
workers = multiprocessing.cpu_count() * 2 + 1

# The type of worker to use.
# The 'sync' worker class is the default and is a good choice for many applications.
# For I/O-bound applications, you might consider using an async worker class
# like 'gevent' or 'uvicorn.workers.UvicornWorker'.
# To use 'gevent', you would need to install it: pip install gevent
# worker_class = 'gevent'
# worker_class = 'uvicorn_worker.UvicornWorker'

# The number of threads to use for each worker.
# This is only applicable for worker classes that support threading (like gthread).
# For the default 'sync' worker, this setting is not used.
# If you were using 'gthread', you might set:
# worker_class = 'gthread'
# threads = 4

# The maximum number of simultaneous clients.
# This setting is only applicable to async worker types (like gevent).
# worker_connections = 1000

# The maximum number of requests a worker will process before restarting.
# This is a simple way to help prevent memory leaks.
# A value of 0 means the worker will never restart.
# NOTE: Set high to avoid ELB health checks (which are very frequent) triggering
# constant worker recycling. Health checks count toward this limit just like
# real requests.
max_requests = 2000

# Adds a random jitter to the max_requests setting.
# This helps prevent all workers from restarting at the same time.
max_requests_jitter = 200

# The timeout for workers.
# If a worker does not respond within this many seconds, it is killed and a new one is started.
# This helps deal with long-running or stuck requests.
timeout = 120

# Keep-Alive timeout.
# The number of seconds to wait for requests on a Keep-Alive connection.
# Generally, this should be set to a low value to prevent workers from being
# tied up waiting for clients.
keepalive = 2

# The log level.
# Options: 'debug', 'info', 'warning', 'error', 'critical'
loglevel = "info"

# The path to the access log file.
# A value of '-' logs to stdout.
accesslog = "-"

# The path to the error log file.
# A value of '-' logs to stderr.
errorlog = "-"

forwarded_allow_ips = "*"

# Preload the application before forking worker processes.
# This can save some memory and speed up server startup.
# However, if you change your application code, you'll need to restart Gunicorn.
preload_app = False

# The directory to which temporary files should be written.
# This may be useful if you have specific filesystem permissions.
# worker_tmp_dir = '/dev/shm'

# Daemonize the Gunicorn process.
# This is not recommended if you are using a process manager like systemd or supervisord,
# which is the standard practice for production deployments.
# daemon = False

# The user and group to run the worker processes as.
# It's a security best practice to run as a non-privileged user.
# user = 'www-data'
# group = 'www-data'

# The path to the Django WSGI application.
# Gunicorn will look for this in the command line, but you can also specify it here.
# Note: It's generally better to pass this on the command line to keep the config generic.
# pythonpath = '/path/to/your/project'
# chdir = '/path/to/your/project'
# raw_env = ['DJANGO_SETTINGS_MODULE=core.settings.staging']
