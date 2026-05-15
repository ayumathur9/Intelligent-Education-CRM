from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/chat/(?P<student_id>\d+)/$", consumers.ChatConsumer.as_asgi()),
    re_path(r"ws/dm/(?P<other_user_id>\d+)/$", consumers.DMConsumer.as_asgi()),
]
