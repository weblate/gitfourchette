import enum


# Python 3.10 compatibility (enum.StrEnum is new in Python 3.11)
if not hasattr(enum, "StrEnum"):
    class _StrEnumCompat(str, enum.Enum):
        def __new__(cls, *values):
            if len(values) != 1 or not isinstance(values[0], str):
                raise ValueError("StrEnum value must be a 1-value tuple containing a string")
            value = str(*values)
            member = str.__new__(cls, value)
            member._value_ = value
            return member

        def __str__(self):
            return self._value_

    enum.StrEnum = _StrEnumCompat
