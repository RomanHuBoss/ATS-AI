"""
MLEOutput — Модель выхода MLE (ML-фильтра)

ТЗ: Appendix B.4 (mle_output)

Immutable Pydantic модель, представляющая решение MLE модели.
Полная совместимость с JSON Schema (contracts/schema/mle_output.json).
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class MLEDecision(str, Enum):
    """
    Решение MLE модели.

    ТЗ: Appendix B.4 (mle_output.decision)
    """

    REJECT = "REJECT"
    WEAK = "WEAK"
    NORMAL = "NORMAL"
    STRONG = "STRONG"


# =============================================================================
# MLE OUTPUT MODEL
# =============================================================================


class MLEOutput(BaseModel):
    """
    Модель выхода MLE (Meta-Labeling Engine).

    ТЗ: Appendix B.4 (mle_output)

    Immutable модель (frozen=True). Содержит решение MLE:
    - Метаданные модели (model_id, artifact_sha256, версии)
    - Решение (decision, risk_mult)
    - Оценки (EV_R_price, вероятности)
    - Ожидаемые издержки (expected_cost_R)
    """

    # Метаданные модели
    schema_version: str = Field(
        ..., pattern="^5$", description="Версия схемы для tracking совместимости"
    )
    model_id: str = Field(..., min_length=1, description="Идентификатор модели")
    artifact_sha256: str = Field(
        ...,
        pattern="^[a-f0-9]{64}$",
        description="SHA256 хэш артефакта модели",
    )
    feature_schema_version: str = Field(
        ..., min_length=1, description="Версия схемы фичей"
    )
    calibration_version: str = Field(
        ..., min_length=1, description="Версия калибровки модели"
    )

    # Решение
    decision: MLEDecision = Field(..., description="Решение MLE (REJECT/WEAK/NORMAL/STRONG)")
    risk_mult: float = Field(..., description="Мультипликатор риска")

    # Оценки
    EV_R_price: float = Field(
        ..., description="Ожидаемое значение в R-единицах (price-edge)"
    )
    p_fail: float = Field(..., ge=0, le=1, description="Вероятность неудачи (0-1)")
    p_neutral: float = Field(..., ge=0, le=1, description="Вероятность нейтрала (0-1)")
    p_success: float = Field(..., ge=0, le=1, description="Вероятность успеха (0-1)")
    p_stopout_noise: Optional[float] = Field(
        None, ge=0, le=1, description="Вероятность stopout noise (0-1, nullable)"
    )

    # Ожидаемые издержки
    expected_cost_R_preMLE: Optional[float] = Field(
        None, description="Ожидаемые издержки до MLE (R-единицы, nullable)"
    )
    expected_cost_R_postMLE: Optional[float] = Field(
        None, description="Ожидаемые издержки после MLE (R-единицы, nullable)"
    )

    model_config = {"frozen": True}
