# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html

from user.models import User
from user.forms import UserChangeForm, UserCreationForm


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    model = User

    list_display = (
        "email",
        "first_name",
        "last_name",
        "tenant",
        "is_staff",
        "is_active",
        "date_joined",
    )
    list_display_links = ("email",)
    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "tenant",
        "date_joined",
    )
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal info"),
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "tenant",
                    "avatar_color",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "tenant",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )

    readonly_fields = ("date_joined", "last_login", "avatar_color")

    def get_form(self, request, obj=None, **kwargs):
        """
        Use special form during user creation in admin
        """
        defaults = {}
        if obj is None:
            defaults["form"] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)


# Optional: if you want to show a small preview of the avatar color
@admin.display(description="Color preview")
def avatar_color_preview(self, obj):
    if obj.avatar_color:
        return format_html(
            '<div style="background-color: {}; width: 24px; height: 24px; '
            'border-radius: 50%; border: 1px solid #ccc; display: inline-block;"></div> {}',
            obj.avatar_color,
            obj.avatar_color,
        )
    return "-"

# You can add this line inside the class if you like the preview:
# avatar_color_preview.allow_tags = True   # only needed in very old Django
# Then add 'avatar_color_preview' to list_display or readonly_fields