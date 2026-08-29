web: gunicorn -c gunicorn.conf.py config.wsgi:application
worker: celery -A config worker --loglevel=info --concurrency=4
beat: celery -A config beat --loglevel=info
release: python manage.py migrate --noinput && python manage.py collectstatic --noinput
