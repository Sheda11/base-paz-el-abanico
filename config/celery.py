import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('base_paz_el_abanico')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'evaluar-morosidad-cartera-medianoche': {
        'task': 'apps.finanzas.tasks.evaluar_cuentas_morosas_medianoche',
        'schedule': crontab(hour=0, minute=0),
        'options': {
            'queue': 'cron_queue',
        },
    },
}
