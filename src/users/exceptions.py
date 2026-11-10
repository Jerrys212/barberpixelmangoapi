from fastapi import status

from src.exceptions import AppError


class EmailAlreadyRegistered(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "EMAIL_ALREADY_REGISTERED"
    message = "El correo ya está registrado"


class UserNotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "USER_NOT_FOUND"
    message = "Usuario no encontrado"


class OwnerAlreadyExists(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "OWNER_ALREADY_EXISTS"
    message = "Ya existe una cuenta de propietario"


class OwnerNotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "OWNER_NOT_FOUND"
    message = "No existe una cuenta de propietario"
