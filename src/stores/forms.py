from django import forms
from .models import Store


class StoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = ['name', 'platform', 'description', 'url', 'active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
