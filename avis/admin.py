from django.contrib import admin

from .models import Avis


@admin.register(Avis)
class AvisAdmin(admin.ModelAdmin):
    list_display = ['terrain', 'amateur', 'note', 'signale', 'visible', 'cree_le']
    list_filter = ['signale', 'visible', 'note']
