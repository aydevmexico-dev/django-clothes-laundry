web: gunicorn -k gevent -w 1 --access-logfile '-' --error-logfile '-' --capture-output core.wsgi:application
release: python manage.py migrate --no-input && python manage.py collectstatic --no-input --clear
