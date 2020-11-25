from logging import getLogger

from django.contrib.auth import get_user_model
from django_rq import job
from typing import List
from django.utils.translation import gettext as _

from voteit.core.models import RoleContextMixin
from voteit.core.queues import DEFAULT_QUEUE
from voteit.messaging.messages.text import TextMessage
from voteit.messaging.signals import client_connect, client_close
from voteit.messaging.utils import update_user_status

logger = getLogger(__name__)

User = get_user_model()


@job(DEFAULT_QUEUE, timeout=5)
def signal_websocket_connect(user_pk: int = None, consumer_name: str = ""):
    user = User.objects.filter(pk=user_pk).first()
    logger.debug("%s connected consumer %s", user_pk, consumer_name)
    update_user_status(user, channel_name=consumer_name, online=True)
    client_connect.send(
        sender=None, user=user, user_pk=user_pk, consumer_name=consumer_name
    )


@job(DEFAULT_QUEUE, timeout=5)
def signal_websocket_close(
    user_pk: int = None, consumer_name: str = "", close_code: int = None
):
    user = User.objects.filter(pk=user_pk).first()
    logger.debug(
        "%s disconnected consumer %s. close_code: %s",
        user_pk,
        consumer_name,
        close_code,
    )
    client_close.send(
        sender=None,
        user=user,
        user_pk=user_pk,
        consumer_name=consumer_name,
        close_code=close_code,
    )
    if user_pk:
        update_user_status(user, channel_name=consumer_name, online=False)


@job(DEFAULT_QUEUE, timeout=20)
def change_roles(
    pk: int,
    userids: List[int],
    roles: List[str],
    message_id: str = None,
    consumer_name: str = None,
    user_pk: int = None,
    permission="__NEVER__",
    model=None,
    action=None
):
    """
    :param pk: id of the instance to perform this action on
    :param userids: The ones to change
    :param roles: roles to assign
    :param message_id:
    :param consumer_name:
    :param user_pk: Who's performing this action
    :param permission: Permission to check
    :param model: The model class
    :param action: "add" or "remove"
    """
    assert issubclass(model, RoleContextMixin)
    context = model.objects.filter(pk=pk).first()
    if context is None:
        msg = TextMessage(message=_("No %(model)s with id %(pk)s" % {"model": model, "pk": pk}))
        msg.send(channel=consumer_name, message_id=message_id, success=False)
        return
    action_user = User.objects.filter(pk=user_pk).first()
    if action_user is None:
        msg = TextMessage(message=_("User with id %(user_pk)s not found" % {"user_pk": user_pk}))
        msg.send(channel=consumer_name, message_id=message_id, success=False)
        return
    if not action_user.has_perm(permission, context):
        msg = TextMessage(message=_("You're not allowed to do this"))
        msg.send(channel=consumer_name, message_id=message_id, success=False)
        return
    users_qs = User.objects.filter(pk__in=userids)
    if len(userids) != users_qs.count():
        msg = TextMessage(message=_("Some userids don't exist"))
        msg.send(channel=consumer_name, message_id=message_id, success=False)
        return
    if action == "add":
        method = context.add_roles
        text = _("Added %(count)s" % {"count": len(userids)})
    elif action == "remove":
        method = context.remove_roles
        text = _("Removed %(count)s" % {"count": len(userids)})
    else:
        raise ValueError("Action must be 'add' or 'remove'")
    for user in User.objects.filter(pk__in=userids):
        method(user, *roles)
    msg = TextMessage(message=text)
    msg.send(channel=consumer_name, message_id=message_id, success=True)
