from sqlalchemy import Enum


def pg_enum(enum_cls: type, native: bool) -> Enum:
    return Enum(
        enum_cls,
        native_enum=native,
        length=None if native else 32,
        values_callable=lambda x: [e.value for e in x],
    )
