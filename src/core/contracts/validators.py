"""
JSON Schema Contract Validators

ТЗ: Appendix B (обязательные схемы контрактов)

Модуль для валидации JSON данных согласно формальным JSON Schema контрактам.
Использует библиотеку jsonschema для проверки соответствия данных схемам.

Схемы:
- market_state.json (Appendix B.1)
- portfolio_state.json (Appendix B.2)
- engine_signal.json (Appendix B.3)
- mle_output.json (Appendix B.4)
"""

import json
from pathlib import Path
from typing import Any, Dict

import jsonschema
from jsonschema import Draft202012Validator, ValidationError


# =============================================================================
# SCHEMA LOADER
# =============================================================================


class SchemaLoader:
    """
    Загрузчик JSON Schema файлов.

    Автоматически находит схемы в contracts/schema/ относительно корня проекта.
    """

    def __init__(self):
        # Определяем корень проекта (4 уровня вверх от этого файла)
        self._schema_dir = Path(__file__).parent.parent.parent.parent / "contracts" / "schema"
        if not self._schema_dir.exists():
            raise RuntimeError(f"Schema directory not found: {self._schema_dir}")

        # Кэш загруженных схем
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def load_schema(self, schema_name: str) -> Dict[str, Any]:
        """
        Загрузка JSON Schema файла.

        Args:
            schema_name: Имя схемы без расширения (например, 'market_state')

        Returns:
            Загруженная схема как dict

        Raises:
            FileNotFoundError: Если файл схемы не найден
            json.JSONDecodeError: Если файл не является валидным JSON
        """
        if schema_name in self._schemas:
            return self._schemas[schema_name]

        schema_path = self._schema_dir / f"{schema_name}.json"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema not found: {schema_path}")

        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        # Валидируем саму схему (meta-validation)
        try:
            Draft202012Validator.check_schema(schema)
        except jsonschema.SchemaError as e:
            raise ValueError(f"Invalid JSON Schema in {schema_name}.json: {e}")

        self._schemas[schema_name] = schema
        return schema


# Глобальный экземпляр загрузчика
_SCHEMA_LOADER = SchemaLoader()


# =============================================================================
# CONTRACT VALIDATORS
# =============================================================================


class ContractValidator:
    """
    Базовый класс для валидаторов контрактов.

    Инкапсулирует логику валидации данных против JSON Schema.
    """

    def __init__(self, schema_name: str):
        """
        Инициализация валидатора.

        Args:
            schema_name: Имя схемы для валидации
        """
        self.schema_name = schema_name
        self.schema = _SCHEMA_LOADER.load_schema(schema_name)
        self.validator = Draft202012Validator(self.schema)

    def validate(self, data: Dict[str, Any]) -> None:
        """
        Валидация данных против схемы.

        Args:
            data: Данные для валидации (dict)

        Raises:
            ValidationError: Если данные не соответствуют схеме
        """
        self.validator.validate(data)

    def is_valid(self, data: Dict[str, Any]) -> bool:
        """
        Проверка валидности данных без exception.

        Args:
            data: Данные для проверки (dict)

        Returns:
            True если данные валидны, False иначе
        """
        return self.validator.is_valid(data)

    def iter_errors(self, data: Dict[str, Any]):
        """
        Итератор по всем ошибкам валидации.

        Args:
            data: Данные для проверки (dict)

        Yields:
            ValidationError объекты для каждой найденной ошибки
        """
        return self.validator.iter_errors(data)


class MarketStateValidator(ContractValidator):
    """
    Валидатор для market_state контракта.

    ТЗ: Appendix B.1
    """

    def __init__(self):
        super().__init__("market_state")


class PortfolioStateValidator(ContractValidator):
    """
    Валидатор для portfolio_state контракта.

    ТЗ: Appendix B.2
    """

    def __init__(self):
        super().__init__("portfolio_state")


class EngineSignalValidator(ContractValidator):
    """
    Валидатор для engine_signal контракта.

    ТЗ: Appendix B.3
    """

    def __init__(self):
        super().__init__("engine_signal")


class MLEOutputValidator(ContractValidator):
    """
    Валидатор для mle_output контракта.

    ТЗ: Appendix B.4
    """

    def __init__(self):
        super().__init__("mle_output")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def validate_market_state(data: Dict[str, Any]) -> None:
    """
    Валидация market_state данных.

    Args:
        data: Данные для валидации

    Raises:
        ValidationError: Если данные не соответствуют схеме
    """
    MarketStateValidator().validate(data)


def validate_portfolio_state(data: Dict[str, Any]) -> None:
    """
    Валидация portfolio_state данных.

    Args:
        data: Данные для валидации

    Raises:
        ValidationError: Если данные не соответствуют схеме
    """
    PortfolioStateValidator().validate(data)


def validate_engine_signal(data: Dict[str, Any]) -> None:
    """
    Валидация engine_signal данных.

    Args:
        data: Данные для валидации

    Raises:
        ValidationError: Если данные не соответствуют схеме
    """
    EngineSignalValidator().validate(data)


def validate_mle_output(data: Dict[str, Any]) -> None:
    """
    Валидация mle_output данных.

    Args:
        data: Данные для валидации

    Raises:
        ValidationError: Если данные не соответствуют схеме
    """
    MLEOutputValidator().validate(data)
