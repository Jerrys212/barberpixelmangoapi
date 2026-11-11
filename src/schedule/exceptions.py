from fastapi import status

from src.exceptions import AppError


class ExceptionNotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "EXCEPTION_NOT_FOUND"
    message = "Excepción de horario no encontrada"


class ExceptionDateInPast(AppError):
    code = "EXCEPTION_DATE_IN_PAST"
    message = "No se pueden crear excepciones en fechas pasadas"


class ExceptionConflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "EXCEPTION_CONFLICT"
    message = "La excepción choca con otra excepción de la misma fecha"


class InvalidDateRange(AppError):
    code = "INVALID_DATE_RANGE"
    message = "Rango de fechas inválido"
