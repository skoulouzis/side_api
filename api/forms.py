from django import forms
from .models import SwitchDocument


class SwitchDocumentForm(forms.ModelForm):

    class Meta:
        model = SwitchDocument
        fields = ('description', 'file', )