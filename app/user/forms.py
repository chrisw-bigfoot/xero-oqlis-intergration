from django.contrib.auth.forms import UserCreationForm, UserChangeForm, AuthenticationForm
from django import forms

from user.models import User


class UserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "tenant",
            # password fields are handled automatically
        )


class UserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


class LoginForm(AuthenticationForm):
    """Custom login form that uses email as the username field"""
    
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        
        # Customize the username field to be for email
        self.fields['username'].label = "Email Address"
        self.fields['username'].widget = forms.EmailInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'your@email.com',
            'autocomplete': 'email',
            'autofocus': True,
        })
        
        # Customize the password field
        self.fields['password'].widget = forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        })

    class Meta:
        model = User
        fields = ('username', 'password')