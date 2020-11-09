from django.urls import path

from . import views

urlpatterns = [
    path('<str:connection_token>/', views.echo, name='echo'),
]
