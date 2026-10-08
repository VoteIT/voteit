from __future__ import annotations

import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand
from django.core.management import CommandError
from django.db import transaction

from voteit.organisation.models import Organisation
from voteit.organisation.roles import ROLE_ORG_MANAGER


class Command(BaseCommand):
    """
    Plain ``createsuperuser`` leaves ``User.organisation`` empty, and nobody can log
    in without an organisation matching the request's ``Host``. Safe to run again.
    """

    help = "Create an organisation for a hostname, optionally with a superuser in it."

    def add_arguments(self, parser):
        parser.add_argument(
            "host",
            help="Hostname without port, e.g. 'localhost' or 'voteit.localhost'.",
        )
        parser.add_argument(
            "--title",
            help="Title of the organisation. Default: the hostname.",
        )
        parser.add_argument(
            "--superuser",
            metavar="USERNAME",
            help="Create a superuser with this username in the organisation, "
            "or attach an existing user without an organisation.",
        )
        parser.add_argument("--email", default="", help="Email of a new superuser.")
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help="Don't prompt for a password. Reads DJANGO_SUPERUSER_PASSWORD instead.",
        )

    def handle(self, *args, **options):
        host = options["host"].split(":")[0].strip().lower()
        if not host:
            raise CommandError("A hostname is required.")
        with transaction.atomic():
            org, created = Organisation.objects.get_or_create(
                host=host, defaults={"title": options["title"] or host}
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created organisation {org.title!r} for {host}")
                )
            else:
                self.stdout.write(
                    f"Using existing organisation {org.title!r} for {host}"
                )
            if username := options["superuser"]:
                self._superuser(org, username, options)

    def _superuser(self, org: Organisation, username: str, options):
        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if user is not None:
            if user.organisation_id not in (None, org.pk):
                raise CommandError(
                    f"User {username!r} already belongs to organisation {user.organisation}."
                )
            user.organisation = org
            user.is_staff = user.is_superuser = True
            user.save(update_fields=["organisation", "is_staff", "is_superuser"])
            msg = f"Attached superuser {username!r} to {org.title!r}"
        else:
            user = User(username=username, email=options["email"], organisation=org)
            password = self._password(user, options["interactive"])
            user = User.objects.create_superuser(
                username=username,
                email=options["email"],
                password=password,
                organisation=org,
            )
            msg = f"Created superuser {username!r} in {org.title!r}"
        org.add_roles(user, ROLE_ORG_MANAGER)
        self.stdout.write(self.style.SUCCESS(f"{msg}, with role {ROLE_ORG_MANAGER}"))

    def _password(self, user, interactive: bool) -> str:
        if not interactive:
            password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
            if not password:
                raise CommandError(
                    "DJANGO_SUPERUSER_PASSWORD must be set when using --noinput."
                )
            return password
        while True:
            password = getpass.getpass()
            if password != getpass.getpass("Password (again): "):
                self.stderr.write("Error: Your passwords didn't match.")
                continue
            try:
                validate_password(password, user)
            except ValidationError as exc:
                self.stderr.write("\n".join(exc.messages))
                bypass = input(
                    "Bypass password validation and create user anyway? [y/N]: "
                )
                if bypass.lower() != "y":
                    continue
            return password
