from django.urls import path
from django.http import HttpResponse

def index(request):
    return HttpResponse('Hello from Django application')

urlpatterns = [
    path('', index),
]
