from voteit.core.rest_api import router

from . import views

router.register("speaker-lists", views.SpeakerListViewSet, basename="speaker-lists")
router.register("speaker-history", views.HistoricSpeakerViewSet, basename="speaker-history")
router.register("speaker-list-systems", views.SpeakerListSystemViewSet)
