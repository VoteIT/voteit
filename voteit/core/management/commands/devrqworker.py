import os
import shlex
import subprocess

from django.core.management.base import BaseCommand
from django.utils import autoreload


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--worker-pid-file",
            action="store",
            dest="worker_pid_file",
            default="/tmp/rqworker.pid",
        )
        parser.add_argument("--with-scheduler", action="store_true")
        parser.add_argument("rqworkerargs", nargs="*")

    def handle(self, *args, **options):
        worker_args = options["rqworkerargs"]
        if options.get("with-scheduler"):
            worker_args.append("--with-scheduler")
        autoreload.run_with_reloader(
            lambda: run_worker(options["worker_pid_file"], options["rqworkerargs"])
        )


def run_worker(worker_pid_file, worker_args):
    if os.path.exists(worker_pid_file):
        worker_pid = subprocess.run(
            ["cat", worker_pid_file], stdout=subprocess.PIPE
        ).stdout.decode("utf-8")
        kill_worker_cmd = f"kill {worker_pid}"
        subprocess.run(shlex.split(kill_worker_cmd), stderr=subprocess.PIPE)

    start_worker_cmd = f'{get_managepy_path()} rqworker --pid={worker_pid_file} {" ".join(worker_args)}'
    print(f"Starting RQ worker: {start_worker_cmd}")
    subprocess.run(shlex.split(start_worker_cmd))


def get_managepy_path() -> str:
    managepy_path = os.path.abspath(os.path.join(os.getcwd(), "manage.py"))
    assert os.path.exists(managepy_path)
    return managepy_path
