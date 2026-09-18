from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any


@dataclass
class AuthResult:
    success: bool
    message: str
    authentication_required: bool = True
    tls_required: bool = True
    secret_generated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "authentication_required": self.authentication_required,
            "tls_required": self.tls_required,
            "secret_generated": self.secret_generated,
        }


def generate_api_secret(
    length: int = 64,
) -> str:
    """
    Generate a cryptographically secure API secret.

    The generated secret is returned to the caller but is
    never written automatically to the configuration file.
    """

    if length < 32:
        raise ValueError(
            "API secret length must be at least 32 characters."
        )

    return secrets.token_urlsafe(length)


def validate_auth_configuration(
    configuration: dict[str, Any],
) -> AuthResult:
    """
    Validate Alcalay authentication and security policy.

    This function does NOT:
        - create users
        - create passwords
        - store passwords
        - create sessions
        - modify PostgreSQL
        - configure TLS certificates
    """

    security = configuration.get(
        "security",
        {},
    )

    authentication_required = bool(
        security.get(
            "authentication_required",
            True,
        )
    )

    tls_required = bool(
        security.get(
            "tls_required",
            True,
        )
    )

    if not authentication_required:
        return AuthResult(
            success=False,
            message=(
                "Authentication must remain enabled "
                "for the Alcalay server."
            ),
            authentication_required=False,
            tls_required=tls_required,
        )

    if not tls_required:
        return AuthResult(
            success=False,
            message=(
                "TLS must remain enabled "
                "for remote Alcalay access."
            ),
            authentication_required=True,
            tls_required=False,
        )

    return AuthResult(
        success=True,
        message=(
            "Authentication and TLS security policy "
            "is valid."
        ),
        authentication_required=True,
        tls_required=True,
    )


def validate_auth_configuration_dict(
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """
    Convenience function for the setup UI.
    """

    return validate_auth_configuration(
        configuration
    ).to_dict()


if __name__ == "__main__":
    print("Alcalay Authentication Setup")
    print("=" * 60)

    configuration = {
        "security": {
            "authentication_required": True,
            "tls_required": True,
        }
    }

    result = validate_auth_configuration(
        configuration
    )

    print(
        f"Status: "
        f"{'OK' if result.success else 'FAILED'}"
    )

    print(
        f"Message: {result.message}"
    )

    print()
    print(
        "Authentication policy is configured."
    )
    print(
        "No users or passwords were created."
    )