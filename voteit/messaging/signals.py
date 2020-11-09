from django.dispatch import Signal

client_connect = Signal(providing_args=["consumer_name", "user", "user_pk"])
client_close = Signal(providing_args=["consumer_name", "user", "user_pk", "close_code"])
