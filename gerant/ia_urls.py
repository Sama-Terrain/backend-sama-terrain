from django.urls import path

from .views import ChatbotView, IAPredictionsView

# Fichier séparé car son préfixe (/api/ia/) est différent de celui de
# urls.py (/api/gerant/), même si la vue vit dans la même app.
urlpatterns = [
    path('predictions/<int:terrain_id>/', IAPredictionsView.as_view(), name='ia-predictions'),
    path('chatbot/', ChatbotView.as_view(), name='ia-chatbot'),
]
