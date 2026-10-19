"""
Cron config for rq's CronScheduler: `python manage.py rqcron voteit.core.cron`

Run exactly one such process. rq's cron scheduler has no lock, so every
running instance enqueues every job.

The jobs modules have already been imported by the apps' ready() at this
point. rqcron clears rq's registry right before importing this module, which
is why @schedule_job collects into its own list instead of calling
rq.cron.register directly.
"""

from rq import cron

from voteit.core.decorators import scheduled_jobs

for _job in scheduled_jobs:
    cron.register(**_job)
