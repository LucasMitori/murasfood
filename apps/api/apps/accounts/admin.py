from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import Address, AuthToken, LoginAttempt, Permission, Role, User, UserRole


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "tenant", "user_type", "is_active", "is_verified", "created_at")
    list_filter = ("user_type", "is_active", "is_verified", "tenant")
    search_fields = ("email", "first_name", "last_name", "phone")
    readonly_fields = ("id", "created_at", "updated_at", "last_login", "anonymized_at")
    filter_horizontal = ("groups", "user_permissions")

    fieldsets = (
        (None, {"fields": ("id", "email", "password", "tenant")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "phone")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "user_type",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_verified",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Consent"), {"fields": ("accepted_terms_at", "marketing_opt_in")}),
        (_("Dates"), {"fields": ("last_login", "created_at", "updated_at", "anonymized_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "tenant", "user_type", "password1", "password2"),
            },
        ),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "tenant", "is_system")
    list_filter = ("is_system", "tenant")
    search_fields = ("name", "slug")
    filter_horizontal = ("permissions",)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "description")
    search_fields = ("code", "description")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "granted_by", "created_at")
    search_fields = ("user__email", "role__name")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("recipient_name", "city", "state", "customer", "is_default")
    search_fields = ("recipient_name", "postal_code", "city", "customer__email")
    list_filter = ("state", "is_default")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("email", "successful", "failure_reason", "ip_address", "created_at")
    list_filter = ("successful", "created_at")
    search_fields = ("email", "ip_address")
    readonly_fields = tuple(f.name for f in LoginAttempt._meta.fields)


@admin.register(AuthToken)
class AuthTokenAdmin(admin.ModelAdmin):
    """Read-only: token hashes exist to be verified, never edited."""

    list_display = ("user", "purpose", "expires_at", "used_at", "created_at")
    list_filter = ("purpose",)
    search_fields = ("user__email",)
    readonly_fields = tuple(f.name for f in AuthToken._meta.fields)
