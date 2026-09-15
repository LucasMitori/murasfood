"""Account serializers."""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer as BaseTokenObtainPairSerializer,
)
from rest_framework_simplejwt.tokens import Token

from apps.common.exceptions import DomainError

from .models import Address, Permission, Role, User
from .services import is_locked_out, record_login_attempt


class InvalidCredentialsError(DomainError):
    default_detail = _("Email or password is incorrect.")
    default_code = "INVALID_CREDENTIALS"
    status_code = 401


@extend_schema_field(
    {
        "type": "object",
        "nullable": True,
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "url": {"type": "string"},
            "variants": {"type": "object", "additionalProperties": {"type": "string"}},
            "placeholder": {"type": "string"},
            "alt_text": {"type": "string"},
        },
    }
)
class AvatarField(serializers.Field):
    """A user's profile picture, rendered the way every other image is.

    Declared as a plain field rather than a nested ``MediaAssetSerializer`` so
    that importing this module does not pull in ``apps.media.serializers`` at
    import time — accounts is imported by nearly everything, and media imports
    storage, which reads settings.
    """

    def to_representation(self, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        from apps.media.serializers import MediaAssetSerializer

        return MediaAssetSerializer(value, context=self.context).data


def _apply_avatar(instance: User, validated_data: dict[str, Any], write: Any) -> User:
    """Resolve ``avatar_id`` to an asset the caller's own tenant owns.

    Accepting a bare id and assigning it would let one merchant point a staff
    photo at another merchant's asset — a cross-tenant read through a foreign
    key, which no amount of queryset scoping elsewhere would catch.
    """
    if "avatar_id" not in validated_data:
        return write(instance, validated_data)

    from apps.media.models import MediaAsset

    asset_id = validated_data.pop("avatar_id")
    if asset_id is None:
        validated_data["avatar"] = None
    else:
        asset = MediaAsset.objects.filter(pk=asset_id, tenant_id=instance.tenant_id).first()
        if asset is None:
            raise serializers.ValidationError({"avatar_id": _("Unknown image.")})
        validated_data["avatar"] = asset

    return write(instance, validated_data)


class PermissionSerializer(serializers.ModelSerializer):
    """One permission, tagged so the UI can separate pages from capabilities."""

    is_page = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = ["id", "code", "description", "is_page", "group"]

    def get_is_page(self, obj: Permission) -> bool:
        from .constants import is_page_permission

        return is_page_permission(obj.code)

    def get_group(self, obj: Permission) -> str:
        """Leading segment, used to group the transfer lists.

        Page codes group under their second segment (`perm.admin.*` -> `admin`)
        because grouping them all under "perm" would be one useless bucket.
        """
        from .constants import is_page_permission

        parts = obj.code.split(".")
        if is_page_permission(obj.code):
            return parts[1] if len(parts) > 1 else "perm"
        return parts[0]


class UserPermissionsSerializer(serializers.Serializer):
    """Read model for the permissions tab of the user editor."""

    direct = serializers.ListField(child=serializers.CharField())
    from_roles = serializers.ListField(child=serializers.CharField())
    effective = serializers.ListField(child=serializers.CharField())


class UserPermissionsWriteSerializer(serializers.Serializer):
    """Replaces the set of *direct* grants. Role permissions are untouched."""

    codes = serializers.ListField(child=serializers.CharField(max_length=64), allow_empty=True)


class UserRolesWriteSerializer(serializers.Serializer):
    """Replaces the set of assigned roles."""

    roles = serializers.ListField(child=serializers.CharField(max_length=64), allow_empty=True)


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SlugRelatedField(
        slug_field="code", many=True, queryset=Permission.objects.all(), required=False
    )

    class Meta:
        model = Role
        fields = ["id", "slug", "name", "description", "is_system", "permissions"]
        read_only_fields = ["id", "is_system"]


class UserSerializer(serializers.ModelSerializer):
    """The authenticated user's own profile."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)
    permissions = serializers.SerializerMethodField()
    roles = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    avatar = AvatarField(read_only=True)
    avatar_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "user_type",
            "is_verified",
            "marketing_opt_in",
            "avatar",
            "avatar_id",
            "roles",
            "permissions",
            "created_at",
        ]
        read_only_fields = ["id", "email", "user_type", "is_verified", "roles", "created_at"]

    def update(self, instance: User, validated_data: dict[str, Any]) -> User:
        return _apply_avatar(instance, validated_data, super().update)

    def get_permissions(self, obj: User) -> list[str]:
        """Permission codes, so the dashboard can hide what the user cannot do.

        The frontend uses this for affordances only — the API re-checks every
        call regardless.
        """
        return sorted(obj.permission_codes())


class CustomerSummarySerializer(serializers.ModelSerializer):
    """Reduced customer view for merchant staff (spec §53: minimise exposure)."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "full_name", "email", "phone", "is_active", "is_verified", "created_at"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)
    first_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    marketing_opt_in = serializers.BooleanField(required=False, default=False)
    accepted_terms = serializers.BooleanField(required=False, default=False)

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class TokenObtainPairSerializer(BaseTokenObtainPairSerializer):
    """Login.

    Adds three things to the stock serializer: tenant-scoped authentication,
    lockout after repeated failures, and tenant/role claims inside the access
    token so downstream services do not need a database round trip.
    """

    default_error_messages: ClassVar[dict[str, str]] = {
        "no_active_account": str(InvalidCredentialsError.default_detail)
    }

    @classmethod
    def get_token(cls, user: User) -> Token:
        token = super().get_token(user)
        token["tenant_id"] = str(user.tenant_id) if user.tenant_id else None
        token["user_type"] = user.user_type
        token["is_verified"] = user.is_verified
        return token

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) if request else None
        email = (attrs.get("email") or "").strip().lower()

        if is_locked_out(email=email, tenant=tenant):
            from .services import AccountLockedError

            raise AccountLockedError()

        user = authenticate(
            request=request,
            username=email,
            password=attrs.get("password"),
            tenant=tenant,
        )

        meta = getattr(request, "META", {}) if request else {}
        ip = meta.get("REMOTE_ADDR")
        user_agent = meta.get("HTTP_USER_AGENT", "")

        if user is None:
            record_login_attempt(
                email=email,
                tenant=tenant,
                successful=False,
                ip=ip,
                user_agent=user_agent,
                failure_reason="invalid_credentials",
            )
            raise InvalidCredentialsError()

        if not user.is_active:
            record_login_attempt(
                email=email,
                tenant=tenant,
                successful=False,
                ip=ip,
                user_agent=user_agent,
                failure_reason="inactive",
            )
            raise InvalidCredentialsError()

        record_login_attempt(
            email=email, tenant=tenant, successful=True, ip=ip, user_agent=user_agent
        )

        refresh = self.get_token(user)
        self.user = user
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        }


class EmailVerificationSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=255)
    uid = serializers.UUIDField(required=False)


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=255)
    uid = serializers.UUIDField(required=False)
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, max_length=128)
    new_password = serializers.CharField(write_only=True, min_length=8, max_length=128)


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "label",
            "recipient_name",
            "postal_code",
            "street",
            "number",
            "complement",
            "neighborhood",
            "city",
            "state",
            "country",
            "reference",
            "latitude",
            "longitude",
            "is_default",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_postal_code(self, value: str) -> str:
        """Keep only digits: users type CEPs with and without a hyphen."""
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) not in (0, 8):
            raise serializers.ValidationError(_("Enter a valid 8-digit postal code."))
        return digits


class StaffUserSerializer(serializers.ModelSerializer):
    """Merchant staff management."""

    roles = serializers.SlugRelatedField(
        slug_field="slug", many=True, queryset=Role.objects.all(), required=False
    )
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    avatar = AvatarField(read_only=True)
    avatar_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "user_type",
            "is_active",
            "is_verified",
            "avatar",
            "avatar_id",
            "roles",
            "created_at",
        ]
        read_only_fields = ["id", "is_verified", "created_at"]

    def update(self, instance: User, validated_data: dict[str, Any]) -> User:
        return _apply_avatar(instance, validated_data, super().update)
