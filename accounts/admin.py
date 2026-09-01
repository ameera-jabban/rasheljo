from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import Address, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin, ModelAdmin):
    # unfold's form classes so the password / permission widgets pick up the theme
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ("email", "first_name", "last_name", "phone", "is_staff")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Storefront", {"fields": ("phone", "preferred_language")}),
    )


@admin.register(Address)
class AddressAdmin(ModelAdmin):
    list_display = ("user", "name", "city", "is_default")
    list_filter = ("city", "is_default")
    list_select_related = ("user",)          # `user` column was 1 query/row
    autocomplete_fields = ("user",)          # was a <select> of every user
    search_fields = ("name", "city", "user__email", "user__first_name", "user__last_name")
