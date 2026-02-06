from django.contrib.auth.forms import UserCreationForm, UserChangeForm

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