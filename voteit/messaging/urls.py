from django.urls import path

from . import views

urlpatterns = [
    path("echo/", views.echo, name="echo"),
    path("msg-browser/", views.message_list),
    path("msg-browser/<str:msg_type>/<str:name>", views.message_show),
]
