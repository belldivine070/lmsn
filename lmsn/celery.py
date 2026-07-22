import os
from celery import Celery
from dotenv import load_dotenv  

load_dotenv()

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lmsn.settings')

app = Celery('lmsn')

# Load configuration from Django settings using the CELERY_ namespace.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# ✅ Windows-safe config
app.conf.worker_pool = 'solo'

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


# Configure Celery Beat Schedule
app.conf.beat_schedule = {
    'check-scheduled-news-every-minute': {
        'task': 'core.tasks.check_scheduled_broadcasts',
        'schedule': 60.0,  # Run every 60 seconds
    },
}