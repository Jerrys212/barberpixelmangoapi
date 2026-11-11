from fastapi import status

from src.exceptions import AppError


class ServiceNotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "SERVICE_NOT_FOUND"
    message = "Servicio no encontrado"
