from __future__ import annotations

import re

from .base import PlateValidationError, PlateValidator, normalize_plate

# Officially used current and historic region codes. Keeping the registry explicit
# prevents accepting an arbitrary three-digit suffix as a valid game asset.
RU_REGION_CODES = frozenset(
    {
        "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39", "40", "41", "42", "43", "44", "45", "46", "47", "48", "49", "50", "51", "52", "53", "54", "55", "56", "57", "58", "59", "60", "61", "62", "63", "64", "65", "66", "67", "68", "69", "70", "71", "72", "73", "74", "75", "76", "77", "78", "79", "80", "81", "82", "83", "84", "85", "86", "87", "89", "90", "91", "92", "93", "94", "95", "96", "97", "98", "99", "102", "103", "109", "113", "116", "118", "121", "123", "124", "125", "126", "134", "136", "138", "142", "147", "150", "152", "154", "156", "159", "161", "163", "164", "173", "174", "175", "177", "178", "180", "181", "184", "186", "190", "193", "196", "197", "198", "199", "716", "750", "752", "754", "761", "763", "774", "777", "790", "797", "799",
    }
)
_PATTERN = re.compile(r"^([АВЕКМНОРСТУХ])([0-9]{3})([АВЕКМНОРСТУХ]{2})([0-9]{2,3})$")


class PlateValidatorRU(PlateValidator):
    country_code = "RU"

    def validate(self, value: str, *, blacklisted_series: set[str] | None = None) -> str:
        plate = normalize_plate(value)
        match = _PATTERN.fullmatch(plate)
        if not match:
            raise PlateValidationError(
                "Формат RU: А000АА77. Используйте только кириллицу из набора АВЕКМНОРСТУХ."
            )
        if match.group(4) not in RU_REGION_CODES:
            raise PlateValidationError("Такого кода региона РФ нет в справочнике.")
        return plate

