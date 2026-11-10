from src.email.sender import OutgoingEmail


def email_verification(to: str, code: str, expire_minutes: int) -> OutgoingEmail:
    return OutgoingEmail(
        to=to,
        subject="Verifica tu correo",
        body=(
            f"Tu código de verificación es: {code}\n\n"
            f"Vence en {expire_minutes} minutos. Si no creaste una cuenta, ignora este correo."
        ),
    )


def password_reset(to: str, code: str, expire_minutes: int) -> OutgoingEmail:
    return OutgoingEmail(
        to=to,
        subject="Recupera tu contraseña",
        body=(
            f"Tu código para restablecer la contraseña es: {code}\n\n"
            f"Vence en {expire_minutes} minutos. Si no lo solicitaste, ignora este correo."
        ),
    )
